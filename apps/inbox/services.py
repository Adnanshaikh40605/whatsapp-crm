import logging

from django.utils import timezone

from apps.core.models import set_current_organization
from apps.crm.models import Contact
from apps.inbox.models import Conversation, Message

logger = logging.getLogger(__name__)
webhook_logger = logging.getLogger("apps.inbox.webhook")


def _normalize_inbound_phone(value: str) -> str:
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if len(digits) == 10:
        return f"91{digits}"
    if digits.startswith("00"):
        return digits[2:]
    return digits


def _broadcast_inbox_message(org, message: Message) -> None:
    from apps.inbox.realtime import broadcast_inbound_message, broadcast_outbound_queued

    org_id = str(org.id)
    if message.direction == Message.Direction.INBOUND:
        broadcast_inbound_message(org_id, message)
    else:
        broadcast_outbound_queued(org_id, message, message.conversation)
    webhook_logger.info(
        "WebSocket broadcast: conversation_id=%s message_id=%s direction=%s",
        message.conversation_id,
        message.id,
        message.direction,
    )


class WebhookProcessor:
    """Handles inbound WhatsApp webhook payloads with bot + AI routing."""

    def __init__(self, payload):
        self.payload = payload

    def process(self):
        entries = self.payload.get("entry", [])
        logger.info("WhatsApp webhook payload summary: entries=%s", len(entries))
        processed = 0
        for entry in entries:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                metadata = value.get("metadata", {})
                phone_number_id = metadata.get("phone_number_id")
                inbound_messages = value.get("messages", [])
                statuses = value.get("statuses", [])

                if inbound_messages or statuses:
                    logger.info(
                        "WhatsApp webhook change: phone_number_id=%s inbound_messages=%s status_events=%s",
                        phone_number_id,
                        len(inbound_messages),
                        [s.get("status") for s in statuses],
                    )

                for msg in inbound_messages:
                    self._process_inbound(msg, phone_number_id, value)
                    processed += 1

                for status in statuses:
                    logger.info(
                        "WhatsApp status webhook: status=%s message_id=%s phone_number_id=%s",
                        status.get("status"),
                        status.get("id"),
                        phone_number_id,
                    )
                    self._process_status(status, phone_number_id)
                    processed += 1
        return {"processed": processed}

    def _get_org(self, phone_number_id):
        from apps.organizations.models import Organization
        return Organization.objects.filter(
            whatsapp_phone_number_id=phone_number_id, is_active=True,
        ).first()

    def _process_inbound(self, msg, phone_number_id, value):
        msg_type_raw = msg.get("type", "text")
        wa_id = msg.get("id", "")
        phone_raw = msg.get("from", "")

        webhook_logger.info(
            "Incoming message webhook: phone_number_id=%s from=%s type=%s text=%s message_id=%s",
            phone_number_id,
            phone_raw,
            msg_type_raw,
            msg.get("text", {}).get("body", "") if msg_type_raw == "text" else "",
            wa_id,
        )

        org = self._get_org(phone_number_id)
        if not org:
            webhook_logger.warning(
                "Incoming webhook: no org for phone_number_id=%s from=%s wamid=%s",
                phone_number_id,
                phone_raw,
                wa_id,
            )
            return

        set_current_organization(org)
        phone = _normalize_inbound_phone(phone_raw)
        if not phone:
            webhook_logger.warning("Incoming webhook: empty customer phone wamid=%s", wa_id)
            return

        if wa_id:
            existing = Message.objects.filter(
                organization=org,
                whatsapp_message_id=wa_id,
            ).first()
            if existing:
                webhook_logger.info(
                    "Incoming webhook duplicate skipped: wamid=%s conversation_id=%s",
                    wa_id,
                    existing.conversation_id,
                )
                return

        contact, _ = Contact.objects.get_or_create(
            organization=org,
            phone=phone,
            defaults={"source": Contact.Source.WHATSAPP, "whatsapp_id": phone_raw or phone},
        )
        if phone_raw and contact.whatsapp_id != phone_raw:
            contact.whatsapp_id = phone_raw
            contact.save(update_fields=["whatsapp_id", "updated_at"])

        conversation, created = Conversation.objects.get_or_create(
            organization=org,
            contact=contact,
            defaults={"status": Conversation.Status.OPEN},
        )

        content, msg_type, button_id = self._extract_content(msg)
        message = Message.objects.create(
            organization=org,
            conversation=conversation,
            direction=Message.Direction.INBOUND,
            message_type=msg_type,
            content=content,
            whatsapp_message_id=wa_id,
            status=Message.Status.DELIVERED,
            metadata={"raw": msg, "button_id": button_id},
        )

        conversation.last_message_at = timezone.now()
        conversation.last_message_preview = content[:255]
        conversation.unread_count += 1
        conversation.metadata = {
            **(conversation.metadata or {}),
            "last_message_direction": Message.Direction.INBOUND,
        }
        conversation.save(update_fields=[
            "last_message_at",
            "last_message_preview",
            "unread_count",
            "metadata",
            "updated_at",
        ])

        webhook_logger.info(
            "Incoming message saved: org=%s conversation_id=%s message_id=%s type=%s",
            org.name,
            conversation.id,
            message.id,
            msg_type,
        )

        try:
            _broadcast_inbox_message(org, message)
        except Exception as exc:
            webhook_logger.warning("WebSocket broadcast failed for inbound message: %s", exc)

        self._track_ad_attribution(org, contact, value)

        if button_id:
            from apps.campaigns.campaign_analytics import track_campaign_click
            try:
                track_campaign_click(org, contact, button_id, content, msg)
            except Exception as exc:
                webhook_logger.warning("Campaign click tracking failed: %s", exc)

        from apps.automation.tasks import dispatch_workflow

        if created:
            dispatch_workflow.delay(str(org.id), "new_message", {
                "phone": phone, "conversation_id": str(conversation.id),
            })

        self._maybe_send_promo_image_reply(org, phone, conversation, content)

    def _maybe_send_promo_image_reply(self, org, phone, conversation, content):
        """Send pest promo image when customer replies HI (opens 24h window for media)."""
        keyword = content.strip().lower()
        if keyword not in {"hi", "hello", "image", "img", "yes", "photo"}:
            return

        from apps.campaigns.promo import get_promo_image_path
        from apps.core.whatsapp_service import WhatsAppService

        image_path = get_promo_image_path()
        if not image_path:
            logger.warning("Promo image file not found on server")
            return

        wa = WhatsAppService(org)
        upload = wa.upload_media_file(image_path, "image/png")
        if upload.get("error"):
            logger.warning("Promo image upload failed: %s", upload["error"])
            return

        import requests

        caption = (
            "Hello! Your pest control offer is ready.\n\n"
            "✅ Mosquito & termite treatment\n"
            "✅ Same-day booking\n"
            "✅ Professional service\n\n"
            "— Pest Control 99"
        )
        url = f"https://graph.facebook.com/v21.0/{org.whatsapp_phone_number_id}/messages"
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {org.whatsapp_access_token}"},
            json={
                "messaging_product": "whatsapp",
                "to": phone,
                "type": "image",
                "image": {"id": upload["id"], "caption": caption[:1024]},
            },
            timeout=30,
        )
        data = response.json()
        if data.get("error"):
            logger.warning("Promo image send failed: %s", data["error"])
            return

        wa_id = (data.get("messages") or [{}])[0].get("id", "")
        outbound = Message.objects.create(
            organization=org,
            conversation=conversation,
            direction=Message.Direction.OUTBOUND,
            message_type=Message.MessageType.IMAGE,
            content=caption,
            whatsapp_message_id=wa_id,
            status=Message.Status.SENT if wa_id else Message.Status.PENDING,
            metadata={"promo_auto_reply": True, "meta_response": data},
        )
        conversation.last_message_preview = "Pest control promo image"
        conversation.last_message_at = timezone.now()
        conversation.metadata = {
            **(conversation.metadata or {}),
            "last_message_direction": Message.Direction.OUTBOUND,
        }
        conversation.save(update_fields=["last_message_preview", "last_message_at", "metadata", "updated_at"])
        logger.info("Sent promo image reply to %s wamid=%s", phone, wa_id)
        try:
            _broadcast_inbox_message(org, outbound)
        except Exception as exc:
            webhook_logger.warning("WebSocket broadcast failed for promo reply: %s", exc)

        # Follow up with Wint-style utility template if approved
        self._try_send_image_template(org, phone, wa, ["Adnan"])

    def _try_send_image_template(self, org, phone, wa, body_params):
        from apps.campaigns.meta import build_template_send_components
        from apps.campaigns.models import WhatsAppTemplate

        tpl = WhatsAppTemplate.objects.filter(
            organization=org,
            name="pest_home_offer",
            status=WhatsAppTemplate.Status.APPROVED,
        ).first()
        if not tpl:
            return
        components = build_template_send_components(tpl, body_params, wa=wa)
        result = wa.send_template(phone, tpl.name, tpl.language, components)
        if result.get("error"):
            logger.warning("pest_home_offer template send failed: %s", result["error"])

    def _extract_content(self, msg):
        msg_type = msg.get("type", "text")
        button_id = ""

        if msg_type == "text":
            return msg.get("text", {}).get("body", ""), Message.MessageType.TEXT, button_id
        if msg_type == "interactive":
            interactive = msg.get("interactive", {})
            if "button_reply" in interactive:
                button_id = interactive["button_reply"].get("id", "")
                return interactive["button_reply"].get("title", button_id), Message.MessageType.INTERACTIVE, button_id
            if "list_reply" in interactive:
                button_id = interactive["list_reply"].get("id", "")
                return interactive["list_reply"].get("title", button_id), Message.MessageType.INTERACTIVE, button_id
        if msg_type == "image":
            return msg.get("image", {}).get("caption", "[Image]"), Message.MessageType.IMAGE, button_id
        if msg_type == "video":
            return msg.get("video", {}).get("caption", "[Video]"), Message.MessageType.VIDEO, button_id
        if msg_type == "document":
            return msg.get("document", {}).get("filename", "[Document]"), Message.MessageType.DOCUMENT, button_id
        if msg_type == "audio":
            return "[Voice note]", Message.MessageType.AUDIO, button_id
        if msg_type == "sticker":
            return "[Sticker]", Message.MessageType.IMAGE, button_id
        if msg_type == "location":
            loc = msg.get("location", {})
            label = loc.get("name") or loc.get("address") or f"{loc.get('latitude')}, {loc.get('longitude')}"
            return f"[Location] {label}".strip(), Message.MessageType.TEXT, button_id
        if msg_type == "contacts":
            names = [
                f"{c.get('name', {}).get('formatted_name', '')}".strip()
                for c in msg.get("contacts", [])
            ]
            return f"[Contact] {', '.join(n for n in names if n) or 'shared'}", Message.MessageType.TEXT, button_id
        return f"[{msg_type}]", Message.MessageType.TEXT, button_id

    def _send_replies(self, org, phone, conversation, replies):
        if not replies:
            return

        from apps.core.whatsapp_service import WhatsAppService
        wa = WhatsAppService(org)

        for reply in replies:
            result = {}
            rtype = reply.get("type", "text")

            if rtype == "text":
                result = wa.send_text(phone, reply.get("body", ""))
                content = reply.get("body", "")
                msg_type = Message.MessageType.TEXT
            elif rtype == "buttons":
                result = wa.send_interactive_buttons(phone, reply["body"], reply.get("buttons", []))
                content = reply["body"]
                msg_type = Message.MessageType.INTERACTIVE
            elif rtype == "list":
                result = wa.send_interactive_list(phone, reply["body"], reply.get("button", "Select"), reply.get("sections", []))
                content = reply["body"]
                msg_type = Message.MessageType.INTERACTIVE
            else:
                continue

            wa_id = ""
            if result.get("messages"):
                wa_id = result["messages"][0].get("id", "")

            Message.objects.create(
                organization=org,
                conversation=conversation,
                direction=Message.Direction.OUTBOUND,
                message_type=msg_type,
                content=content,
                whatsapp_message_id=wa_id,
                status=Message.Status.SENT,
                metadata={"bot_reply": True},
            )
            conversation.last_message_preview = content[:255]
            conversation.last_message_at = timezone.now()
            conversation.save(update_fields=["last_message_preview", "last_message_at", "updated_at"])

    def _process_status(self, status, phone_number_id):
        org = self._get_org(phone_number_id)
        if not org:
            logger.warning(
                "WhatsApp status webhook: no org for phone_number_id=%s",
                phone_number_id,
            )
            return

        set_current_organization(org)
        wa_id = status.get("id", "")
        msg_status = status.get("status", "")

        from apps.inbox.message_status import (
            apply_message_status_update,
            buffer_pending_status,
            find_message_for_wa_status,
        )

        message = find_message_for_wa_status(org, wa_id)
        if not message:
            status_map = {
                "sent": Message.Status.SENT,
                "delivered": Message.Status.DELIVERED,
                "read": Message.Status.READ,
                "failed": Message.Status.FAILED,
            }
            new_status = status_map.get(msg_status)
            if new_status and wa_id:
                buffer_pending_status(
                    wa_id,
                    status=new_status,
                    event_time=status.get("timestamp"),
                    raw_payload=status,
                )
                webhook_logger.info(
                    "WhatsApp status buffered (message not ready): status=%s wamid=%s",
                    msg_status,
                    wa_id,
                )
            else:
                webhook_logger.warning(
                    "WhatsApp status webhook: no message found for wamid=%s org=%s",
                    wa_id,
                    org.name,
                )
            return

        status_map = {
            "sent": Message.Status.SENT,
            "delivered": Message.Status.DELIVERED,
            "read": Message.Status.READ,
            "failed": Message.Status.FAILED,
        }
        new_status = status_map.get(msg_status)
        if not new_status:
            return

        apply_message_status_update(
            message,
            new_status,
            event_time=status.get("timestamp"),
            raw_payload=status,
            broadcast=True,
        )
        logger.info(
            "WhatsApp status applied: status=%s message_id=%s db_message_id=%s",
            msg_status,
            wa_id,
            message.id,
        )

        from apps.campaigns.models import CampaignRecipient
        now = timezone.now()
        recipient = CampaignRecipient.objects.filter(whatsapp_message_id=wa_id).first()
        if recipient:
            if msg_status == "delivered":
                recipient.status = CampaignRecipient.Status.DELIVERED
                recipient.delivered_at = now
            elif msg_status == "read":
                recipient.status = CampaignRecipient.Status.READ
                recipient.read_at = now
            elif msg_status == "failed":
                recipient.status = CampaignRecipient.Status.FAILED
                if status.get("errors"):
                    recipient.error_message = str(status.get("errors"))
                    from apps.campaigns.campaign_analytics import _parse_failure_code
                    recipient.failure_code = _parse_failure_code(recipient.error_message)
            recipient.save()
            campaign = recipient.campaign
            campaign.sent_count = campaign.recipients.filter(status__in=[
                CampaignRecipient.Status.SENT,
                CampaignRecipient.Status.DELIVERED,
                CampaignRecipient.Status.READ,
                CampaignRecipient.Status.REPLIED,
                CampaignRecipient.Status.CLICKED,
            ]).count()
            campaign.delivered_count = campaign.recipients.filter(status__in=[
                CampaignRecipient.Status.DELIVERED,
                CampaignRecipient.Status.READ,
                CampaignRecipient.Status.REPLIED,
                CampaignRecipient.Status.CLICKED,
            ]).count()
            campaign.read_count = campaign.recipients.filter(status__in=[
                CampaignRecipient.Status.READ,
                CampaignRecipient.Status.REPLIED,
                CampaignRecipient.Status.CLICKED,
            ]).count()
            campaign.failed_count = campaign.recipients.filter(status=CampaignRecipient.Status.FAILED).count()
            campaign.save(update_fields=[
                "sent_count",
                "delivered_count",
                "read_count",
                "failed_count",
                "updated_at",
            ])

    def _track_ad_attribution(self, org, contact, value):
        from apps.campaigns.models import AdAttribution

        referral = value.get("messages", [{}])[0].get("referral", {}) if value.get("messages") else {}
        if not referral:
            return

        source_type = referral.get("source_type", "")
        source = AdAttribution.Source.ORGANIC
        if "facebook" in source_type.lower() or referral.get("source_url", "").find("fb") >= 0:
            source = AdAttribution.Source.FACEBOOK
        elif "instagram" in source_type.lower():
            source = AdAttribution.Source.INSTAGRAM

        AdAttribution.objects.create(
            organization=org,
            source=source,
            campaign_name=referral.get("headline", ""),
            ad_id=referral.get("source_id", ""),
            contact=contact,
            metadata=referral,
        )

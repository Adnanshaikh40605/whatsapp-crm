import logging

from django.utils import timezone

from apps.core.models import set_current_organization
from apps.crm.models import Contact
from apps.inbox.models import Conversation, Message

logger = logging.getLogger(__name__)


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
        org = self._get_org(phone_number_id)
        if not org:
            return

        set_current_organization(org)
        phone = msg.get("from", "")
        contact, _ = Contact.objects.get_or_create(
            organization=org, phone=phone,
            defaults={"source": Contact.Source.WHATSAPP, "whatsapp_id": phone},
        )

        conversation, created = Conversation.objects.get_or_create(
            organization=org, contact=contact,
            defaults={"status": Conversation.Status.OPEN},
        )

        content, msg_type, button_id = self._extract_content(msg)
        Message.objects.create(
            organization=org,
            conversation=conversation,
            direction=Message.Direction.INBOUND,
            message_type=msg_type,
            content=content,
            whatsapp_message_id=msg.get("id", ""),
            status=Message.Status.DELIVERED,
            metadata={"raw": msg},
        )

        conversation.last_message_at = timezone.now()
        conversation.last_message_preview = content[:255]
        conversation.unread_count += 1
        conversation.save(update_fields=["last_message_at", "last_message_preview", "unread_count", "updated_at"])

        self._track_ad_attribution(org, contact, value)

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
        Message.objects.create(
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
        conversation.save(update_fields=["last_message_preview", "last_message_at", "updated_at"])
        logger.info("Sent promo image reply to %s wamid=%s", phone, wa_id)

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

        message = Message.objects.filter(organization=org, whatsapp_message_id=wa_id).first()
        if not message:
            logger.warning(
                "WhatsApp status webhook: no message found for wamid=%s org=%s",
                wa_id,
                org.name,
            )
            return

        now = timezone.now()
        status_map = {
            "sent": Message.Status.SENT,
            "delivered": Message.Status.DELIVERED,
            "read": Message.Status.READ,
            "failed": Message.Status.FAILED,
        }
        message.status = status_map.get(msg_status, message.status)
        message.metadata = {
            **(message.metadata or {}),
            "last_status_webhook_at": now.isoformat(),
            "last_status_payload": status,
            "status_timestamps": {
                **(message.metadata or {}).get("status_timestamps", {}),
                msg_status: status.get("timestamp") or now.isoformat(),
            },
        }
        if msg_status == "failed" and status.get("errors"):
            message.metadata["errors"] = status.get("errors")
        message.save(update_fields=["status", "metadata", "updated_at"])
        logger.info(
            "WhatsApp status applied: status=%s message_id=%s db_message_id=%s",
            msg_status,
            wa_id,
            message.id,
        )

        from apps.campaigns.models import CampaignRecipient
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

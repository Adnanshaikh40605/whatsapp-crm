"""Shared helpers for embed inbox + customer APIs."""

from django.utils import timezone

from apps.crm.models import Contact
from apps.inbox.models import Conversation, Message
from apps.inbox.serializers import MessageSerializer
from apps.inbox.tasks import send_whatsapp_message


def normalize_phone(value: str) -> str:
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if len(digits) == 10:
        return f"91{digits}"
    if digits.startswith("00"):
        return digits[2:]
    return digits


def contact_display_name(contact: Contact) -> str:
    return contact.full_name


def serialize_conversation_list_item(conversation: Conversation) -> dict:
    contact = conversation.contact
    return {
        "id": str(conversation.id),
        "customer": contact_display_name(contact),
        "phone": contact.phone,
        "unread_count": conversation.unread_count,
        "last_message": conversation.last_message_preview or "",
        "last_message_time": (
            conversation.last_message_at.isoformat() if conversation.last_message_at else None
        ),
        "status": conversation.status,
    }


def serialize_conversation_detail(conversation: Conversation) -> dict:
    messages = Message.objects.filter(conversation=conversation).order_by("created_at")
    return {
        **serialize_conversation_list_item(conversation),
        "messages": [
            {
                "id": str(msg.id),
                "direction": msg.direction,
                "type": msg.message_type,
                "content": msg.content,
                "status": msg.status,
                "sent_at": msg.sent_at.isoformat() if msg.sent_at else None,
                "delivered_at": msg.delivered_at.isoformat() if msg.delivered_at else None,
                "read_at": msg.read_at.isoformat() if msg.read_at else None,
                "created_at": msg.created_at.isoformat(),
            }
            for msg in messages
        ],
    }


def serialize_customer(contact: Contact) -> dict:
    return {
        "id": str(contact.id),
        "name": contact_display_name(contact),
        "phone": contact.phone,
        "email": contact.email,
        "company": contact.company,
        "whatsapp_id": contact.whatsapp_id,
        "tags": contact.tags,
        "custom_fields": contact.custom_fields,
        "last_contacted_at": (
            contact.last_contacted_at.isoformat() if contact.last_contacted_at else None
        ),
    }


def queue_outbound_message(
    *,
    organization,
    user,
    conversation: Conversation,
    content: str,
    message_type: str = Message.MessageType.TEXT,
    media_url: str = "",
    template_name: str = "",
    template_language: str = "en",
    template_components: list | None = None,
) -> Message:
    message = Message.objects.create(
        organization=organization,
        conversation=conversation,
        channel=Message.Channel.WHATSAPP,
        direction=Message.Direction.OUTBOUND,
        message_type=message_type,
        content=content,
        media_url=media_url,
        template_name=template_name,
        sender=user,
        metadata={
            "template_language": template_language,
            "template_components": template_components or [],
            "embed_api": True,
        },
    )
    now = timezone.now()
    conversation.last_message_at = now
    conversation.last_message_preview = content[:255]
    conversation.metadata = {
        **(conversation.metadata or {}),
        "last_message_direction": Message.Direction.OUTBOUND,
    }
    conversation.save(update_fields=["last_message_at", "last_message_preview", "metadata", "updated_at"])

    from apps.inbox.message_status import apply_message_status_update
    from apps.inbox.realtime import broadcast_inbox_event

    apply_message_status_update(message, Message.Status.PENDING, broadcast=False)
    org_id = str(organization.id)
    message_data = MessageSerializer(message).data
    broadcast_inbox_event(org_id, {"type": "message_sent", "message": message_data})
    broadcast_inbox_event(org_id, {"type": "message_created", "message": message_data})
    send_whatsapp_message.delay(str(message.id))
    return message


def get_or_create_conversation(organization, contact: Contact) -> Conversation:
    conversation, _ = Conversation.objects.get_or_create(
        organization=organization,
        contact=contact,
        defaults={"status": Conversation.Status.OPEN},
    )
    return conversation


def resolve_conversation(org, data):
    if data.get("conversation_id"):
        return Conversation.objects.select_related("contact").get(
            id=data["conversation_id"],
            organization=org,
        )
    phone = normalize_phone(data.get("phone", ""))
    contact, _ = Contact.objects.get_or_create(
        organization=org,
        phone=phone,
        defaults={"source": Contact.Source.API, "is_active": True},
    )
    return get_or_create_conversation(org, contact)

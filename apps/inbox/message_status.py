"""Central WhatsApp message delivery status updates + realtime broadcast."""

from datetime import datetime, timezone as dt_timezone

from django.utils import timezone

from apps.inbox.models import Conversation, Message
from apps.inbox.realtime import broadcast_message_status


STATUS_RANK = {
    Message.Status.PENDING: 0,
    Message.Status.SENDING: 1,
    Message.Status.SENT: 2,
    Message.Status.DELIVERED: 3,
    Message.Status.READ: 4,
    Message.Status.FAILED: 99,
}


def parse_meta_timestamp(value) -> datetime:
    if not value:
        return timezone.now()
    try:
        return datetime.fromtimestamp(int(value), tz=dt_timezone.utc)
    except (TypeError, ValueError):
        return timezone.now()


def _extract_error_reason(payload: dict | None) -> str:
    if not payload:
        return ""
    errors = payload.get("errors") or []
    if not errors:
        return ""
    first = errors[0]
    return first.get("message") or first.get("title") or str(first)


def should_apply_status(current: str, new: str) -> bool:
    if new == Message.Status.FAILED:
        return True
    if current == Message.Status.FAILED:
        return False
    return STATUS_RANK.get(new, 0) >= STATUS_RANK.get(current, 0)


def serialize_message_status(message: Message) -> dict:
    return {
        "type": "message_status_updated",
        "message": {
            "id": str(message.id),
            "conversation_id": str(message.conversation_id),
            "status": message.status,
            "whatsapp_message_id": message.whatsapp_message_id,
            "sent_at": message.sent_at.isoformat() if message.sent_at else None,
            "delivered_at": message.delivered_at.isoformat() if message.delivered_at else None,
            "read_at": message.read_at.isoformat() if message.read_at else None,
            "failed_at": message.failed_at.isoformat() if message.failed_at else None,
            "error_reason": message.error_reason or None,
        },
        "conversation": {
            "id": str(message.conversation_id),
            "last_outbound_status": message.conversation.last_outbound_status,
        },
    }


def apply_message_status_update(
    message: Message,
    new_status: str,
    *,
    event_time=None,
    error_reason: str = "",
    raw_payload: dict | None = None,
    broadcast: bool = True,
) -> Message:
    if not should_apply_status(message.status, new_status):
        return message

    now = parse_meta_timestamp(event_time) if event_time else timezone.now()
    message.status = new_status

    if new_status == Message.Status.SENDING:
        pass
    elif new_status == Message.Status.SENT and not message.sent_at:
        message.sent_at = now
    elif new_status == Message.Status.DELIVERED and not message.delivered_at:
        message.delivered_at = now
    elif new_status == Message.Status.READ and not message.read_at:
        message.read_at = now
        if not message.delivered_at:
            message.delivered_at = now
    elif new_status == Message.Status.FAILED:
        message.failed_at = now
        message.error_reason = error_reason or _extract_error_reason(raw_payload)

    if raw_payload:
        message.metadata = {
            **(message.metadata or {}),
            "last_status_payload": raw_payload,
            "last_status_webhook_at": timezone.now().isoformat(),
        }

    update_fields = [
        "status",
        "sent_at",
        "delivered_at",
        "read_at",
        "failed_at",
        "error_reason",
        "metadata",
        "updated_at",
    ]
    message.save(update_fields=update_fields)

    if message.direction == Message.Direction.OUTBOUND and not message.is_internal_note:
        Conversation.objects.filter(id=message.conversation_id).update(
            last_outbound_status=new_status,
            updated_at=timezone.now(),
        )
        message.conversation.refresh_from_db(fields=["last_outbound_status"])

    if broadcast:
        broadcast_message_status(message)

    return message

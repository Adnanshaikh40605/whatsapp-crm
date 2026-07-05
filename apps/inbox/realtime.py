"""Inbox WebSocket broadcast helpers (Django Channels + Redis)."""

import logging

from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)


def broadcast_inbox_event(org_id: str, payload: dict) -> None:
    """Publish a single event to the org inbox channel group."""
    try:
        from channels.layers import get_channel_layer

        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        async_to_sync(channel_layer.group_send)(
            f"inbox_{org_id}",
            {
                "type": "inbox_event",
                "data": payload,
            },
        )
    except Exception as exc:
        logger.warning("Inbox broadcast failed: %s", exc)


def broadcast_inbox_events(org_id: str, payloads: list[dict]) -> None:
    """Publish multiple distinct events (no deduplication across types)."""
    for payload in payloads:
        broadcast_inbox_event(org_id, payload)


def serialize_ws_message(message) -> dict:
    """Message payload for WebSocket clients (embed + main app)."""
    from apps.inbox.serializers import MessageSerializer

    data = dict(MessageSerializer(message).data)
    data["conversation_id"] = str(message.conversation_id)
    return data


def serialize_conversation_updated(conversation) -> dict:
    """Lightweight conversation_updated payload for CRM list patches."""
    updated_at = conversation.updated_at.isoformat() if conversation.updated_at else None
    last_message_at = (
        conversation.last_message_at.isoformat() if conversation.last_message_at else None
    )
    return {
        "type": "conversation_updated",
        "event": "conversation_updated",
        "conversation_id": str(conversation.id),
        "last_message": conversation.last_message_preview or "",
        "unread_count": conversation.unread_count,
        "updated_at": updated_at,
        "last_message_at": last_message_at,
        # Backward compatibility for WhatsFlow main app
        "conversation": {
            "id": str(conversation.id),
            "last_message_preview": conversation.last_message_preview or "",
            "last_message_at": last_message_at,
            "unread_count": conversation.unread_count,
            "last_outbound_status": conversation.last_outbound_status or "",
            "metadata": conversation.metadata or {},
            "updated_at": updated_at,
        },
    }


def broadcast_conversation_updated(org_id: str, conversation) -> None:
    broadcast_inbox_event(org_id, serialize_conversation_updated(conversation))


def broadcast_inbound_message(org_id: str, message) -> None:
    """Inbound webhook: new_message + message_created + conversation_updated."""
    message_data = serialize_ws_message(message)
    conversation = message.conversation
    broadcast_inbox_events(
        org_id,
        [
            {"type": "new_message", "message": message_data},
            {"type": "message_created", "message": message_data},
            serialize_conversation_updated(conversation),
        ],
    )


def broadcast_outbound_queued(org_id: str, message, conversation) -> None:
    """Outbound queued (before Meta API): message_sent + message_created + conversation_updated."""
    message_data = serialize_ws_message(message)
    broadcast_inbox_events(
        org_id,
        [
            {"type": "message_sent", "message": message_data},
            {"type": "message_created", "message": message_data},
            serialize_conversation_updated(conversation),
        ],
    )


def broadcast_message_status(
    message,
    *,
    include_conversation_update: bool = True,
    include_embed_alias: bool = True,
) -> None:
    """Delivery status from Meta webhook or send task."""
    from apps.inbox.message_status import serialize_message_status

    org_id = str(message.organization_id)
    payload = serialize_message_status(message)
    events = [payload]

    if include_embed_alias:
        embed_type = {
            "sent": "message_sent",
            "delivered": "message_delivered",
            "read": "message_read",
        }.get(message.status)
        if embed_type:
            events.append({**payload, "type": embed_type})

    if include_conversation_update:
        message.conversation.refresh_from_db()
        events.append(serialize_conversation_updated(message.conversation))

    broadcast_inbox_events(org_id, events)

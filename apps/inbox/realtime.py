import logging

from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)


def broadcast_inbox_event(org_id: str, payload: dict) -> None:
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

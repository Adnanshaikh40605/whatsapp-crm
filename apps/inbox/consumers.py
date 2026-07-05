import json
import logging
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken

logger = logging.getLogger(__name__)
User = get_user_model()


class InboxConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.org_id = self.scope["url_route"]["kwargs"]["org_id"]
        self.room_group_name = f"inbox_{self.org_id}"

        user = await self._authenticate_user()
        if user is None:
            await self.close()
            return

        self.scope["user"] = user
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        await self.send_json({"type": "connected", "org_id": self.org_id})

    async def disconnect(self, close_code):
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive_json(self, content):
        event_type = content.get("type")
        if event_type == "ping":
            await self.send_json({"type": "pong"})
        elif event_type == "typing":
            await self.channel_layer.group_send(
                self.room_group_name,
                {"type": "inbox_event", "data": {"type": "typing", **content}},
            )
        elif event_type == "presence":
            await self.channel_layer.group_send(
                self.room_group_name,
                {"type": "inbox_event", "data": {"type": "presence", **content}},
            )

    async def inbox_event(self, event):
        await self.send_json(event["data"])

    async def new_message(self, event):
        await self.send_json(event["data"])

    async def conversation_updated(self, event):
        await self.send_json(event["data"])

    @database_sync_to_async
    def _authenticate_user(self):
        user = self.scope.get("user")
        if user and not getattr(user, "is_anonymous", True):
            return user

        query = parse_qs(self.scope.get("query_string", b"").decode())
        token = (query.get("token") or [None])[0]
        if not token:
            return None
        try:
            validated = AccessToken(token)
            user_id = validated.get("user_id")
            return User.objects.filter(id=user_id, is_active=True).first()
        except (InvalidToken, TokenError, KeyError) as exc:
            logger.debug("Inbox websocket auth failed: %s", exc)
            return None

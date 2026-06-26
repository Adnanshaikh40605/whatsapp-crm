import json

from channels.generic.websocket import AsyncJsonWebsocketConsumer


class InboxConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.org_id = self.scope["url_route"]["kwargs"]["org_id"]
        self.room_group_name = f"inbox_{self.org_id}"

        if self.scope["user"].is_anonymous:
            await self.close()
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive_json(self, content):
        event_type = content.get("type")
        if event_type == "ping":
            await self.send_json({"type": "pong"})

    async def new_message(self, event):
        await self.send_json(event["data"])

    async def conversation_updated(self, event):
        await self.send_json(event["data"])

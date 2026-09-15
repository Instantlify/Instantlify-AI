from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.tenants.models import Membership


class InboxConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.workspace_id = self.scope["url_route"]["kwargs"]["workspace_id"]
        if not self.scope["user"].is_authenticated or not await self.is_member():
            await self.close(code=4403)
            return
        self.group = f"workspace.{self.workspace_id}"
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    @database_sync_to_async
    def is_member(self):
        return (
            Membership.objects.for_workspace(self.workspace_id)
            .filter(user_id=self.scope["user"].id)
            .exists()
        )

    async def workspace_changed(self, event):
        if not await self.is_member():
            await self.close(code=4403)
            return
        # No customer data is broadcast. Authorized API reads enforce assignment.
        await self.send_json({"type": "refresh"})

    async def disconnect(self, code):
        if hasattr(self, "group"):
            await self.channel_layer.group_discard(self.group, self.channel_name)

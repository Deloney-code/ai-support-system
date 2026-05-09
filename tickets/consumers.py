import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser


class DashboardConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for the real-time agent dashboard.

    Security:
    - Unauthenticated users are disconnected immediately
    - Only agents can join the dashboard group
    - No sensitive data (passwords, emails) is ever broadcast
    """

    async def connect(self):
        self.user = self.scope.get('user')

        # Security check 1 — reject unauthenticated connections
        if not self.user or isinstance(self.user, AnonymousUser):
            await self.close(code=4001)
            return

        # Security check 2 — reject non-agents
        is_agent = await self.get_user_role()
        if not is_agent:
            await self.close(code=4003)
            return

        # Join the agents dashboard group
        self.group_name = 'dashboard_agents'
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )

    async def receive(self, text_data):
        # Clients don't send data to this consumer
        # It's a one-way broadcast from server to client
        pass

    async def ticket_update(self, event):
        """
        Called when a ticket.update message is sent to the group.
        Forwards the event data to the WebSocket client.
        Only safe, non-sensitive fields are included.
        """
        await self.send(text_data=json.dumps({
            'type': 'ticket_update',
            'ticket_id': event['ticket_id'],
            'title': event['title'],
            'status': event['status'],
            'priority': event['priority'],
            'category': event['category'],
            'owner': event['owner'],
        }))

    async def ticket_new(self, event):
        """
        Called when a new ticket is created.
        Broadcasts basic ticket info to all connected agents.
        """
        await self.send(text_data=json.dumps({
            'type': 'ticket_new',
            'ticket_id': event['ticket_id'],
            'title': event['title'],
            'status': event['status'],
            'priority': event['priority'],
            'category': event['category'],
            'owner': event['owner'],
        }))

    @database_sync_to_async
    def get_user_role(self):
        return self.user.is_agent()
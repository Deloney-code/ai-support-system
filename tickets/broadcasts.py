from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def broadcast_new_ticket(ticket):
    """
    Broadcasts a new ticket event to all connected agents.
    Called after a ticket is created.
    Only safe fields are included — no PII.
    """
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        'dashboard_agents',
        {
            'type': 'ticket_new',
            'ticket_id': ticket.pk,
            'title': ticket.title,
            'status': ticket.get_status_display(),
            'priority': ticket.get_priority_display(),
            'category': ticket.get_category_display(),
            'owner': ticket.owner.username,
        }
    )


def broadcast_ticket_update(ticket):
    """
    Broadcasts a ticket status update to all connected agents.
    Called when status or priority changes.
    """
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        'dashboard_agents',
        {
            'type': 'ticket_update',
            'ticket_id': ticket.pk,
            'title': ticket.title,
            'status': ticket.get_status_display(),
            'priority': ticket.get_priority_display(),
            'category': ticket.get_category_display(),
            'owner': ticket.owner.username,
        }
    )
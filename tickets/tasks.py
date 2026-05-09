from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def send_ticket_confirmation_email(self, ticket_id):
    try:
        from .models import Ticket
        ticket = Ticket.objects.select_related('owner').get(pk=ticket_id)

        send_mail(
            subject=f"Ticket #{ticket.pk} received — {ticket.title}",
            message=f"""Hi {ticket.owner.first_name or ticket.owner.username},

Your support ticket has been received and our team will be in touch shortly.

Ticket details:
- Title: {ticket.title}
- Category: {ticket.get_category_display()}
- Priority: {ticket.get_priority_display()}
- Status: {ticket.get_status_display()}

Thank you for contacting support.
""",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[ticket.owner.email],
            fail_silently=False,
        )
        logger.info(f"Confirmation email sent for ticket #{ticket_id}")

    except Exception as exc:
        logger.error(f"Email failed for ticket #{ticket_id}: {exc}")
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True, max_retries=3)
def auto_resolve_ticket(self, ticket_id):
    try:
        from .models import Ticket, TicketComment
        from .ai_service import auto_resolve_check
        from django.contrib.auth import get_user_model

        User = get_user_model()
        ticket = Ticket.objects.get(pk=ticket_id)

        if ticket.status != 'open':
            return

        result = auto_resolve_check(ticket.title, ticket.description)

        if result['can_resolve'] and result['suggested_reply']:
            system_user, _ = User.objects.get_or_create(
                username='support-bot',
                defaults={
                    'email': 'bot@support.com',
                    'role': 'agent',
                    'is_active': True,
                }
            )

            TicketComment.objects.create(
                ticket=ticket,
                author=system_user,
                body=result['suggested_reply']
            )

            ticket.status = 'resolved'
            ticket.save()
            from .broadcasts import broadcast_ticket_update
            broadcast_ticket_update(ticket)

            logger.info(f"Ticket #{ticket_id} auto-resolved by AI")
            send_ticket_resolution_email.delay(ticket_id)

    except Exception as exc:
        logger.error(f"Auto-resolve failed for ticket #{ticket_id}: {exc}")
        raise self.retry(exc=exc, countdown=30)


@shared_task(bind=True, max_retries=3)
def send_ticket_resolution_email(self, ticket_id):
    try:
        from .models import Ticket
        ticket = Ticket.objects.select_related('owner').get(pk=ticket_id)

        send_mail(
            subject=f"Ticket #{ticket.pk} resolved — {ticket.title}",
            message=f"""Hi {ticket.owner.first_name or ticket.owner.username},

Good news! Your support ticket has been resolved.

Ticket: {ticket.title}

Please log in to view the full resolution details.
If you need further assistance, feel free to open a new ticket.

Thank you.
""",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[ticket.owner.email],
            fail_silently=False,
        )

    except Exception as exc:
        logger.error(f"Resolution email failed for ticket #{ticket_id}: {exc}")
        raise self.retry(exc=exc, countdown=60)


@shared_task
def classify_new_ticket(ticket_id):
    try:
        from .models import Ticket
        from .ai_service import classify_ticket

        ticket = Ticket.objects.get(pk=ticket_id)
        result = classify_ticket(ticket.title, ticket.description)

        ticket.category = result['category']
        ticket.priority = result['priority']
        ticket.save(update_fields=['category', 'priority'])

        logger.info(f"Ticket #{ticket_id} auto-classified: {result}")

    except Exception as exc:
        logger.error(f"Classification failed for ticket #{ticket_id}: {exc}")
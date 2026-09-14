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

        if not ticket.owner.email:
            logger.info(f"No email for ticket #{ticket_id} owner, skipping")
            return

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

        # Get or create the AI support bot user
        system_user, _ = User.objects.get_or_create(
            username='support-bot',
            defaults={
                'email': 'bot@supportiq.com',
                'role': 'agent',
                'is_active': True,
            }
        )

        result = auto_resolve_check(ticket.title, ticket.description)

        if result['can_resolve'] and result['suggested_reply']:
            # AI can resolve — post reply and close ticket
            TicketComment.objects.create(
                ticket=ticket,
                author=system_user,
                body=result['suggested_reply']
            )

            ticket.status = 'resolved'
            ticket.assigned_to = system_user
            ticket.save()

            logger.info(f"Ticket #{ticket_id} auto-resolved by AI")

            if ticket.owner.email:
                send_ticket_resolution_email.delay(ticket_id)

        else:
            # AI cannot resolve — post acknowledgment and escalate
            TicketComment.objects.create(
                ticket=ticket,
                author=system_user,
                body=f"""Hi {ticket.owner.first_name or ticket.owner.username},

Thank you for reaching out to SupportIQ. I have reviewed your request regarding "{ticket.title}".

This issue requires attention from one of our specialist agents. I have escalated your ticket to our support team who will review it and get back to you shortly.

In the meantime, please feel free to add any additional information or screenshots that might help us resolve your issue faster.

Your ticket reference is #{ticket.pk}. Please keep this for your records.

Best regards,
SupportIQ AI Assistant"""
            )

            ticket.status = 'in_progress'
            ticket.save()

            logger.info(f"Ticket #{ticket_id} escalated to human agent by AI")

    except Exception as exc:
        logger.error(f"Auto-resolve failed for ticket #{ticket_id}: {exc}")
        raise self.retry(exc=exc, countdown=30)


@shared_task(bind=True, max_retries=3)
def send_ticket_resolution_email(self, ticket_id):
    try:
        from .models import Ticket
        ticket = Ticket.objects.select_related('owner').get(pk=ticket_id)

        if not ticket.owner.email:
            return

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
        logger.info(f"Resolution email sent for ticket #{ticket_id}")

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


@shared_task(bind=True, max_retries=3)
def process_inbound_email(self, inbound_email_id):
    try:
        from .models import InboundEmail, Ticket, TicketComment
        from .ai_service import auto_resolve_check, generate_email_reply
        from django.contrib.auth import get_user_model

        User = get_user_model()
        inbound = InboundEmail.objects.get(pk=inbound_email_id)

        system_user, _ = User.objects.get_or_create(
            username='support-bot',
            defaults={
                'email': 'bot@supportiq.com',
                'role': 'agent',
                'is_active': True,
            }
        )

        customer, _ = User.objects.get_or_create(
            email=inbound.sender,
            defaults={
                'username': inbound.sender.split('@')[0][:30],
                'role': 'customer',
                'is_active': True,
            }
        )

        ticket = Ticket.objects.create(
            title=inbound.subject or 'Email Support Request',
            description=inbound.body,
            owner=customer,
            category='general',
            priority='medium',
            status='open',
        )

        result = auto_resolve_check(ticket.title, ticket.description)

        if result['can_resolve'] and result['suggested_reply']:
            TicketComment.objects.create(
                ticket=ticket,
                author=system_user,
                body=result['suggested_reply']
            )
            ticket.status = 'resolved'
            ticket.assigned_to = system_user
            ticket.save()

            logger.info(f"Email ticket #{ticket.pk} auto-resolved by AI")
            send_email_reply.delay(ticket.pk, inbound.sender, result['suggested_reply'])
        else:
            ticket.status = 'in_progress'
            ticket.save()

        inbound.processed = True
        inbound.save()

    except Exception as exc:
        logger.error(f"Failed to process inbound email #{inbound_email_id}: {exc}")
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True, max_retries=3)
def send_email_reply(self, ticket_id, recipient_email, reply_text):
    try:
        from .models import Ticket
        ticket = Ticket.objects.get(pk=ticket_id)

        send_mail(
            subject=f"Re: {ticket.title}",
            message=reply_text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
            fail_silently=False,
        )
        logger.info(f"Email reply sent to {recipient_email} for ticket #{ticket_id}")

    except Exception as exc:
        logger.error(f"Failed to send email reply for ticket #{ticket_id}: {exc}")
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True, max_retries=3)
def send_ticket_resolution_email(self, ticket_id):
    try:
        from .models import Ticket
        ticket = Ticket.objects.select_related('owner').get(pk=ticket_id)

        if not ticket.owner.email:
            return

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
        logger.info(f"Resolution email sent for ticket #{ticket_id}")

    except Exception as exc:
        logger.error(f"Resolution email failed for ticket #{ticket_id}: {exc}")
        raise self.retry(exc=exc, countdown=60)
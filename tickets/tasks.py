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

        @shared_task(bind=True, max_retries=3)
def process_inbound_email(self, inbound_email_id):
    """
    Processes an inbound email from Mailgun:
    1. Creates a ticket from the email
    2. Runs AI to attempt auto-resolution
    3. Sends reply back to customer
    4. Escalates to agent if AI cannot resolve
    """
    try:
        from .models import InboundEmail, Ticket, TicketComment
        from .ai_service import generate_email_reply, classify_ticket
        from django.contrib.auth import get_user_model
        import re

        User = get_user_model()
        inbound = InboundEmail.objects.get(pk=inbound_email_id)

        if inbound.processed:
            return

        # Get or create a customer account for this email sender
        sender_name = inbound.sender.split('@')[0].replace('.', ' ').title()
        customer, created = User.objects.get_or_create(
            email=inbound.sender,
            defaults={
                'username': re.sub(r'[^a-zA-Z0-9]', '_', inbound.sender.split('@')[0])[:30],
                'first_name': sender_name.split()[0] if ' ' in sender_name else sender_name,
                'role': 'customer',
            }
        )

        if created:
            customer.set_unusable_password()
            customer.save()

        # Get or create support bot user
        bot_user, _ = User.objects.get_or_create(
            username='support-bot',
            defaults={
                'email': 'bot@support.com',
                'role': 'agent',
                'is_active': True,
            }
        )

        # Classify the ticket
        classification = classify_ticket(inbound.subject, inbound.body)

        # Create the ticket
        ticket = Ticket.objects.create(
            owner=customer,
            title=inbound.subject[:200],
            description=inbound.body,
            category=classification['category'],
            priority=classification['priority'],
            status='open',
        )

        inbound.ticket = ticket
        inbound.save()

        # Broadcast new ticket to agents dashboard
        from .broadcasts import broadcast_new_ticket
        broadcast_new_ticket(ticket)

        # Run AI to attempt auto-resolution
        ai_result = generate_email_reply(
            ticket.title,
            ticket.description,
            sender_name
        )

        if ai_result['can_resolve'] and ai_result['confidence'] in ['high', 'medium']:
            # AI can handle it — post reply and resolve ticket
            TicketComment.objects.create(
                ticket=ticket,
                author=bot_user,
                body=f"[AI Auto-Reply]\n{ai_result['reply']}"
            )
            ticket.status = 'resolved'
            ticket.save()

            # Send email reply back to customer
            send_email_reply.delay(
                to_email=inbound.sender,
                to_name=sender_name,
                subject=f"Re: {inbound.subject}",
                body=ai_result['reply'],
                ticket_id=ticket.pk
            )

            logger.info(f"Email ticket #{ticket.pk} auto-resolved by AI")

        else:
            # AI cannot resolve — escalate to human agent
            ticket.status = 'open'
            ticket.save()

            TicketComment.objects.create(
                ticket=ticket,
                author=bot_user,
                body="[AI Agent] This ticket requires human attention and has been escalated to our support team."
            )

            # Send acknowledgement email to customer
            send_email_reply.delay(
                to_email=inbound.sender,
                to_name=sender_name,
                subject=f"Re: {inbound.subject}",
                body=f"""Hi {sender_name},

Thank you for contacting our support team.

We have received your message and created a support ticket (#{ticket.pk}) for you.
One of our agents will review your case and get back to you shortly.

In the meantime, you can track your ticket status by logging into our support portal.

Best regards,
Support Team""",
                ticket_id=ticket.pk
            )

            logger.info(f"Email ticket #{ticket.pk} escalated to human agent")

        inbound.processed = True
        inbound.save()

    except Exception as exc:
        logger.error(f"Failed to process inbound email #{inbound_email_id}: {exc}")
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True, max_retries=3)
def send_email_reply(self, to_email, to_name, subject, body, ticket_id):
    """Sends an email reply back to the customer."""
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to_email],
            fail_silently=False,
        )
        logger.info(f"Email reply sent to {to_email} for ticket #{ticket_id}")
    except Exception as exc:
        logger.error(f"Failed to send email reply to {to_email}: {exc}")
        raise self.retry(exc=exc, countdown=60)
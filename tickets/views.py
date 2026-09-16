import hashlib
import hmac
import time
import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count, Q

from .models import Ticket, TicketComment, InboundEmail
from .forms import TicketForm, TicketCommentForm, TicketStatusForm
from .ai_service import summarize_ticket, polish_reply, classify_ticket, auto_resolve_check
from .tasks import classify_new_ticket, auto_resolve_ticket, send_ticket_confirmation_email

logger = logging.getLogger(__name__)
User = get_user_model()


@login_required
def dashboard(request):
    user = request.user

    if user.is_superuser or user.is_staff:
        all_tickets = Ticket.objects.select_related('owner', 'assigned_to').all()
        total_count = all_tickets.count()
        open_count = all_tickets.filter(status='open').count()
        in_progress_count = all_tickets.filter(status='in_progress').count()
        resolved_count = all_tickets.filter(status='resolved').count()
        unassigned_count = all_tickets.filter(assigned_to=None, status__in=['open', 'in_progress']).count()

        agents = User.objects.filter(
            Q(role='agent') | Q(is_staff=True)
        ).annotate(
            ticket_count=Count('assigned_tickets', filter=Q(assigned_tickets__status__in=['open', 'in_progress']))
        ).order_by('-ticket_count')

        from django.utils import timezone
        from datetime import timedelta
        at_risk = all_tickets.filter(
            status='open',
            created_at__lt=timezone.now() - timedelta(hours=24)
        ).order_by('created_at')[:5]

        unassigned_tickets = all_tickets.filter(
            assigned_to=None,
            status__in=['open', 'in_progress']
        ).order_by('created_at')[:10]

        recent_tickets = all_tickets.order_by('-created_at')[:10]

        return render(request, 'tickets/admin_dashboard.html', {
            'total_count': total_count,
            'open_count': open_count,
            'in_progress_count': in_progress_count,
            'resolved_count': resolved_count,
            'unassigned_count': unassigned_count,
            'agents': agents,
            'at_risk': at_risk,
            'unassigned_tickets': unassigned_tickets,
            'recent_tickets': recent_tickets,
        })

    elif hasattr(user, 'role') and user.role == 'agent':
        tickets = Ticket.objects.select_related('owner', 'assigned_to').all()
        total_count = tickets.count()
        open_count = tickets.filter(status='open').count()
        in_progress_count = tickets.filter(status='in_progress').count()
        resolved_count = tickets.filter(status='resolved').count()

        from django.core.paginator import Paginator
        paginator = Paginator(tickets.order_by('-created_at'), 15)
        page_obj = paginator.get_page(request.GET.get('page'))

        return render(request, 'tickets/dashboard.html', {
            'page_obj': page_obj,
            'total_count': total_count,
            'open_count': open_count,
            'in_progress_count': in_progress_count,
            'resolved_count': resolved_count,
        })

    else:
        tickets = Ticket.objects.filter(owner=user).select_related('owner', 'assigned_to')
        total_count = tickets.count()
        open_count = tickets.filter(status='open').count()
        in_progress_count = tickets.filter(status='in_progress').count()
        resolved_count = tickets.filter(status='resolved').count()

        from django.core.paginator import Paginator
        paginator = Paginator(tickets.order_by('-created_at'), 15)
        page_obj = paginator.get_page(request.GET.get('page'))

        return render(request, 'tickets/dashboard.html', {
            'page_obj': page_obj,
            'total_count': total_count,
            'open_count': open_count,
            'in_progress_count': in_progress_count,
            'resolved_count': resolved_count,
        })


@login_required
def team_view(request):
    if not (request.user.is_superuser or request.user.is_staff):
        return redirect('tickets:dashboard')

    agents = User.objects.filter(
        Q(role='agent') | Q(is_staff=True)
    ).annotate(
        open_count=Count('assigned_tickets', filter=Q(assigned_tickets__status='open')),
        in_progress_count=Count('assigned_tickets', filter=Q(assigned_tickets__status='in_progress')),
        resolved_count=Count('assigned_tickets', filter=Q(assigned_tickets__status='resolved')),
        total_count=Count('assigned_tickets'),
    ).order_by('-open_count')

    unassigned = Ticket.objects.filter(
        assigned_to=None,
        status__in=['open', 'in_progress']
    ).select_related('owner').order_by('created_at')

    return render(request, 'tickets/team.html', {
        'agents': agents,
        'unassigned': unassigned,
    })


@login_required
def customers_view(request):
    if not (request.user.is_superuser or request.user.is_staff):
        return redirect('tickets:dashboard')

    customers = User.objects.filter(role='customer').annotate(
        total_tickets=Count('tickets'),
        open_tickets=Count('tickets', filter=Q(tickets__status='open')),
        resolved_tickets=Count('tickets', filter=Q(tickets__status='resolved')),
    ).order_by('-total_tickets')

    return render(request, 'tickets/customers.html', {
        'customers': customers,
    })


@login_required
def assign_ticket(request, pk):
    if not (request.user.is_superuser or request.user.is_staff):
        return redirect('tickets:dashboard')

    ticket = get_object_or_404(Ticket, pk=pk)

    if request.method == 'POST':
        agent_id = request.POST.get('agent_id')
        if agent_id:
            agent = get_object_or_404(User, pk=agent_id)
            ticket.assigned_to = agent
            ticket.status = 'in_progress'
            ticket.save()
            messages.success(request, f'Ticket #{ticket.pk} assigned to {agent.get_full_name() or agent.username}')
        else:
            ticket.assigned_to = None
            ticket.save()
            messages.info(request, f'Ticket #{ticket.pk} unassigned')

    return redirect(request.META.get('HTTP_REFERER', 'tickets:dashboard'))


@login_required
def ticket_create(request):
    form = TicketForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        ticket = form.save(commit=False)
        ticket.owner = request.user
        ticket.save()
        send_ticket_confirmation_email.delay(ticket.pk)
        classify_new_ticket.delay(ticket.pk)
        auto_resolve_ticket.delay(ticket.pk)
        messages.success(request, f'Ticket #{ticket.pk} created.')
        return redirect('tickets:ticket_detail', pk=ticket.pk)
    return render(request, 'tickets/ticket_form.html', {'form': form, 'action': 'Create'})


@login_required
def ticket_detail(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)

    if not (request.user.is_staff or request.user == ticket.owner or
            (hasattr(request.user, 'role') and request.user.role == 'agent')):
        messages.error(request, 'You do not have permission to view this ticket.')
        return redirect('tickets:dashboard')

    comment_form = TicketCommentForm(request.POST or None)
    if request.method == 'POST' and comment_form.is_valid():
        comment = comment_form.save(commit=False)
        comment.ticket = ticket
        comment.author = request.user
        comment.save()
        return redirect('tickets:ticket_detail', pk=pk)

    comments = ticket.comments.select_related('author').order_by('created_at')
    agents = User.objects.filter(Q(role='agent') | Q(is_staff=True))
    status_form = TicketStatusForm(instance=ticket)

    return render(request, 'tickets/ticket_detail.html', {
        'ticket': ticket,
        'comments': comments,
        'comment_form': comment_form,
        'status_form': status_form,
        'agents': agents,
    })


@login_required
def ticket_edit(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    if request.user != ticket.owner and not request.user.is_staff:
        messages.error(request, 'Permission denied.')
        return redirect('tickets:dashboard')

    form = TicketForm(request.POST or None, instance=ticket)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Ticket updated.')
        return redirect('tickets:ticket_detail', pk=pk)
    return render(request, 'tickets/ticket_form.html', {'form': form, 'action': 'Edit'})


@login_required
@require_POST
def ticket_close(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    if request.user != ticket.owner and not request.user.is_staff:
        messages.error(request, 'Permission denied.')
        return redirect('tickets:dashboard')
    ticket.status = 'closed'
    ticket.save()
    messages.success(request, f'Ticket #{pk} closed.')
    return redirect('tickets:dashboard')


@login_required
@require_POST
def ticket_status_update(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    if not (request.user.is_staff or hasattr(request.user, 'role') and request.user.role == 'agent'):
        messages.error(request, 'Permission denied.')
        return redirect('tickets:ticket_detail', pk=pk)

    form = TicketStatusForm(request.POST, instance=ticket)
    if form.is_valid():
        form.save()
        messages.success(request, 'Ticket updated.')
    return redirect('tickets:ticket_detail', pk=pk)


@login_required
@require_POST
def ai_summarize(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    result = summarize_ticket(ticket.title, ticket.description)
    return JsonResponse(result)


@login_required
@require_POST
def ai_polish_reply(request, pk):
    rough = request.POST.get('rough_reply', '')
    result = polish_reply(rough)
    return JsonResponse(result)


@login_required
@require_POST
def ai_classify(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    result = classify_ticket(ticket.title, ticket.description)
    return JsonResponse(result)


@login_required
@require_POST
def ai_auto_resolve(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    result = auto_resolve_check(ticket.title, ticket.description)
    return JsonResponse(result)


@login_required
@require_POST
def toggle_auto_reply(request):
    if not (request.user.is_superuser or request.user.is_staff):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    from .models import SupportSettings
    from django.utils import timezone

    support_settings = SupportSettings.get()
    support_settings.auto_reply_enabled = not support_settings.auto_reply_enabled
    support_settings.auto_reply_changed_by = request.user
    support_settings.auto_reply_changed_at = timezone.now()
    support_settings.save()

    return JsonResponse({
        'enabled': support_settings.auto_reply_enabled,
        'message': f"Auto-reply {'enabled' if support_settings.auto_reply_enabled else 'disabled'}"
    })


@csrf_exempt
def mailgun_webhook(request):
    if request.method != 'POST':
        return HttpResponse(status=405)

    mailgun_api_key = getattr(settings, 'MAILGUN_API_KEY', '')
    if not mailgun_api_key:
        logger.error('Mailgun webhook: MAILGUN_API_KEY not set — rejecting request')
        return HttpResponse(status=403)

    token = request.POST.get('token', '')
    timestamp = request.POST.get('timestamp', '')
    signature = request.POST.get('signature', '')

    value = f'{timestamp}{token}'.encode()
    expected = hmac.new(mailgun_api_key.encode(), value, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected, signature):
        logger.warning('Mailgun webhook: invalid signature')
        return HttpResponse(status=403)

    try:
        ts = int(timestamp)
        if abs(time.time() - ts) > 300:
            return HttpResponse(status=403)
    except (ValueError, TypeError):
        return HttpResponse(status=400)

    sender = request.POST.get('sender') or request.POST.get('from', '')
    subject = request.POST.get('subject', 'Support Request')
    body = request.POST.get('body-plain') or request.POST.get('body-html', '')

    if not sender or not body:
        return HttpResponse(status=400)

    inbound = InboundEmail.objects.create(
        sender=sender,
        subject=subject,
        body=body,
        raw_payload=request.POST.dict(),
    )

    from .tasks import process_inbound_email
    process_inbound_email.delay(inbound.pk)

    return HttpResponse(status=200)
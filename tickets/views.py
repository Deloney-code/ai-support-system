from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_http_methods, require_POST
from django.http import JsonResponse
from .models import Ticket, TicketComment
from .forms import TicketForm, TicketCommentForm, TicketStatusForm
from . import ai_service
from .broadcasts import broadcast_new_ticket, broadcast_ticket_update


def check_ticket_owner_or_agent(user, ticket):
    if not (ticket.owner == user or user.is_agent()):
        raise PermissionDenied


@login_required
def dashboard(request):
    if request.user.is_agent():
        tickets = Ticket.objects.select_related('owner', 'assigned_to').all()
    else:
        tickets = Ticket.objects.filter(owner=request.user)

    context = {
        'tickets': tickets,
        'open_count': tickets.filter(status='open').count(),
        'in_progress_count': tickets.filter(status='in_progress').count(),
        'resolved_count': tickets.filter(status='resolved').count(),
    }
    return render(request, 'tickets/dashboard.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def ticket_create(request):
    form = TicketForm(request.POST or None)

    if request.method == 'POST':
        if form.is_valid():
            ticket = form.save(commit=False)
            ticket.owner = request.user
            ticket.save()
            broadcast_new_ticket(ticket)

            from .tasks import (
                send_ticket_confirmation_email,
                auto_resolve_ticket,
                classify_new_ticket
            )
            send_ticket_confirmation_email.delay(ticket.pk)
            auto_resolve_ticket.delay(ticket.pk)
            classify_new_ticket.delay(ticket.pk)

            messages.success(request, "Ticket created successfully.")
            return redirect('tickets:ticket_detail', pk=ticket.pk)
        else:
            messages.error(request, "Please correct the errors below.")

    return render(request, 'tickets/ticket_form.html', {
        'form': form,
        'action': 'Create'
    })


@login_required
def ticket_detail(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    check_ticket_owner_or_agent(request.user, ticket)

    comment_form = TicketCommentForm(request.POST or None)
    status_form = TicketStatusForm(instance=ticket) if request.user.is_agent() else None

    if request.method == 'POST' and comment_form.is_valid():
        comment = comment_form.save(commit=False)
        comment.ticket = ticket
        comment.author = request.user
        comment.save()
        messages.success(request, "Comment added.")
        return redirect('tickets:ticket_detail', pk=pk)

    return render(request, 'tickets/ticket_detail.html', {
        'ticket': ticket,
        'comment_form': comment_form,
        'status_form': status_form,
        'comments': ticket.comments.select_related('author').all(),
    })


@login_required
@require_http_methods(["GET", "POST"])
def ticket_edit(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    check_ticket_owner_or_agent(request.user, ticket)

    if ticket.status not in ['open', 'in_progress']:
        messages.error(request, "Resolved or closed tickets cannot be edited.")
        return redirect('tickets:ticket_detail', pk=pk)

    form = TicketForm(request.POST or None, instance=ticket)

    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, "Ticket updated.")
            return redirect('tickets:ticket_detail', pk=pk)

    return render(request, 'tickets/ticket_form.html', {
        'form': form,
        'action': 'Edit',
        'ticket': ticket
    })


@login_required
@require_http_methods(["POST"])
def ticket_close(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    check_ticket_owner_or_agent(request.user, ticket)
    ticket.status = 'closed'
    ticket.save()
    messages.success(request, "Ticket closed.")
    return redirect('tickets:dashboard')


@login_required
@require_http_methods(["POST"])
def ticket_status_update(request, pk):
    if not request.user.is_agent():
        raise PermissionDenied

    ticket = get_object_or_404(Ticket, pk=pk)
    form = TicketStatusForm(request.POST, instance=ticket)

    if form.is_valid():
        updated_ticket = form.save()
        broadcast_ticket_update(updated_ticket)
        messages.success(request, "Ticket status updated.")
    else:
        messages.error(request, "Invalid status update.")

    return redirect('tickets:ticket_detail', pk=pk)


@login_required
@require_POST
def ai_polish_reply(request, pk):
    if not request.user.is_agent():
        raise PermissionDenied

    ticket = get_object_or_404(Ticket, pk=pk)
    rough_reply = request.POST.get('rough_reply', '').strip()

    if not rough_reply:
        return JsonResponse({'error': 'No reply text provided.'}, status=400)

    try:
        polished = ai_service.polish_reply(
            rough_reply,
            ticket.title,
            ticket.description
        )
        return JsonResponse({'polished_reply': polished})
    except Exception:
        return JsonResponse({'error': 'AI service unavailable.'}, status=503)


@login_required
@require_POST
def ai_summarize(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    check_ticket_owner_or_agent(request.user, ticket)

    comments = list(ticket.comments.select_related('author').values(
        'author__username', 'body'
    ))
    comment_list = [
        {'author': c['author__username'], 'body': c['body']}
        for c in comments
    ]

    try:
        summary = ai_service.summarize_ticket(
            ticket.title,
            ticket.description,
            comment_list
        )
        return JsonResponse({'summary': summary})
    except Exception:
        return JsonResponse({'error': 'AI service unavailable.'}, status=503)


@login_required
@require_POST
def ai_classify(request, pk):
    if not request.user.is_agent():
        raise PermissionDenied

    ticket = get_object_or_404(Ticket, pk=pk)

    try:
        classification = ai_service.classify_ticket(
            ticket.title,
            ticket.description
        )
        return JsonResponse(classification)
    except Exception:
        return JsonResponse({'error': 'AI service unavailable.'}, status=503)


@login_required
@require_POST
def ai_auto_resolve(request, pk):
    if not request.user.is_agent():
        raise PermissionDenied

    ticket = get_object_or_404(Ticket, pk=pk)

    try:
        result = ai_service.auto_resolve_check(
            ticket.title,
            ticket.description
        )
        return JsonResponse(result)
    except Exception:
        return JsonResponse({'error': 'AI service unavailable.'}, status=503)
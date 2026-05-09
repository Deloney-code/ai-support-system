import anthropic
import bleach
from django.conf import settings


# Initialize the client once — it reads ANTHROPIC_API_KEY from your .env
client = anthropic.Anthropic()


def _safe_ai_response(text: str) -> str:
    """
    Every AI response passes through this before touching
    the database or being rendered in a template.
    Prevents prompt injection from escalating into XSS.
    """
    return bleach.clean(
        text,
        tags=['p', 'b', 'i', 'ul', 'li', 'br', 'strong', 'em'],
        strip=True
    )


def polish_reply(rough_reply: str, ticket_title: str, ticket_description: str) -> str:
    """
    Takes an agent's rough draft and returns a polished,
    professional customer support reply.
    """
    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": f"""You are a professional customer support agent.
Polish the following draft reply into a clear, empathetic, and professional
customer support response. Keep the same meaning but improve the tone and clarity.

Ticket title: {ticket_title}
Ticket description: {ticket_description}

Draft reply to polish:
{rough_reply}

Return only the polished reply text, nothing else."""
            }
        ]
    )
    raw = message.content[0].text
    return _safe_ai_response(raw)


def summarize_ticket(ticket_title: str, ticket_description: str, comments: list) -> str:
    """
    Produces a concise summary of the ticket and its comment thread.
    Useful for agents picking up a ticket mid-conversation.
    """
    comment_thread = "\n".join([
        f"{c['author']}: {c['body']}" for c in comments
    ])

    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": f"""Summarize this customer support ticket in 3-4 sentences.
Include the core issue, any steps already taken, and current status.

Title: {ticket_title}
Description: {ticket_description}
Comment thread:
{comment_thread if comment_thread else "No comments yet."}

Return only the summary, nothing else."""
            }
        ]
    )
    raw = message.content[0].text
    return _safe_ai_response(raw)


def classify_ticket(ticket_title: str, ticket_description: str) -> dict:
    """
    Suggests a category and priority for a ticket based on its content.
    Returns a dict with 'category' and 'priority' keys.
    Falls back to safe defaults if parsing fails.
    """
    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=128,
        messages=[
            {
                "role": "user",
                "content": f"""Classify this customer support ticket.

Title: {ticket_title}
Description: {ticket_description}

Reply with exactly two lines:
CATEGORY: one of [billing, technical, general, account, other]
PRIORITY: one of [low, medium, high, critical]

Nothing else."""
            }
        ]
    )

    raw = message.content[0].text.strip()
    result = {'category': 'general', 'priority': 'medium'}  # safe defaults

    for line in raw.splitlines():
        if line.startswith('CATEGORY:'):
            value = line.split(':', 1)[1].strip().lower()
            if value in ['billing', 'technical', 'general', 'account', 'other']:
                result['category'] = value
        elif line.startswith('PRIORITY:'):
            value = line.split(':', 1)[1].strip().lower()
            if value in ['low', 'medium', 'high', 'critical']:
                result['priority'] = value

    return result


def auto_resolve_check(ticket_title: str, ticket_description: str) -> dict:
    """
    Checks if a ticket is a common simple request that can be
    auto-resolved. Returns a dict with:
      - 'can_resolve': bool
      - 'suggested_reply': str (empty if can_resolve is False)
    """
    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": f"""You are a customer support AI.
Determine if this ticket is a simple, common request that can be
resolved with a standard response (e.g. password reset instructions,
business hours, return policy, basic how-to questions).

Title: {ticket_title}
Description: {ticket_description}

Reply with exactly:
CAN_RESOLVE: yes or no
REPLY: (if yes, write the full resolution reply; if no, write nothing after REPLY:)"""
            }
        ]
    )

    raw = message.content[0].text.strip()
    result = {'can_resolve': False, 'suggested_reply': ''}

    lines = raw.splitlines()
    for i, line in enumerate(lines):
        if line.startswith('CAN_RESOLVE:'):
            value = line.split(':', 1)[1].strip().lower()
            result['can_resolve'] = value == 'yes'
        elif line.startswith('REPLY:'):
            reply_text = line.split(':', 1)[1].strip()
            # Grab any continuation lines after REPLY:
            for continuation in lines[i+1:]:
                reply_text += '\n' + continuation
            result['suggested_reply'] = _safe_ai_response(reply_text.strip())

    return result
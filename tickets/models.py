from django.db import models
from django.conf import settings
import bleach


class Ticket(models.Model):

    STATUS_CHOICES = [
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ]

    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]

    CATEGORY_CHOICES = [
        ('billing', 'Billing'),
        ('technical', 'Technical'),
        ('general', 'General'),
        ('account', 'Account'),
        ('other', 'Other'),
    ]

    # Ownership — ForeignKey uses ORM, never raw SQL
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tickets'
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_tickets'
    )

    title = models.CharField(max_length=200)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='general')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        # Sanitize before every save — XSS protection at the model level
        self.title = bleach.clean(self.title, tags=[], strip=True)
        self.description = bleach.clean(
            self.description,
            tags=['p', 'b', 'i', 'ul', 'li', 'br'],
            strip=True
        )
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.status.upper()}] {self.title}"


class TicketComment(models.Model):
    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,
        related_name='comments'
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def save(self, *args, **kwargs):
        # Sanitize comment body — strip all HTML from comments
        self.body = bleach.clean(self.body, tags=[], strip=True)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Comment by {self.author.username} on Ticket #{self.ticket.id}"

class InboundEmail(models.Model):
    """Tracks emails received from customers via Mailgun webhook."""
    sender = models.EmailField()
    subject = models.CharField(max_length=255)
    body = models.TextField()
    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inbound_emails'
    )
    received_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)

    def __str__(self):
        return f"Email from {self.sender}: {self.subject}"
# Create your models here.

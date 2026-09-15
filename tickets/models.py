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
        self.body = bleach.clean(self.body, tags=[], strip=True)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Comment by {self.author.username} on Ticket #{self.ticket.id}"


class InboundEmail(models.Model):
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


class SupportSettings(models.Model):
    """
    Singleton model for support system settings.
    Only one row should exist — use SupportSettings.get() to access.
    """
    auto_reply_enabled = models.BooleanField(
        default=False,
        help_text="When ON, AI automatically replies to new tickets. When OFF, agents reply manually."
    )
    auto_reply_changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='settings_changes'
    )
    auto_reply_changed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Support Settings'
        verbose_name_plural = 'Support Settings'

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return f"Support Settings (auto_reply={'ON' if self.auto_reply_enabled else 'OFF'})"
        class SupportSettings(models.Model):
    """
    Singleton model for support system settings.
    Only one row should exist — use SupportSettings.get() to access.
    """
    auto_reply_enabled = models.BooleanField(
        default=False,
        help_text="When ON, AI automatically replies to new tickets. When OFF, agents reply manually."
    )
    auto_reply_changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='settings_changes'
    )
    auto_reply_changed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Support Settings'
        verbose_name_plural = 'Support Settings'

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return f"Support Settings (auto_reply={'ON' if self.auto_reply_enabled else 'OFF'})"
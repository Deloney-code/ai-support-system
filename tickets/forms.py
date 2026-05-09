from django import forms
from .models import Ticket, TicketComment
import bleach


class TicketForm(forms.ModelForm):
    """
    Used for both creating and editing tickets.
    Bleach runs at the model level on save, but we also
    validate here to catch issues before they hit the DB.
    """
    class Meta:
        model = Ticket
        fields = ['title', 'description', 'priority', 'category']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 5}),
        }

    def clean_title(self):
        title = self.cleaned_data.get('title', '')
        cleaned = bleach.clean(title, tags=[], strip=True)
        if not cleaned.strip():
            raise forms.ValidationError("Title cannot be empty or contain only HTML.")
        return cleaned

    def clean_description(self):
        description = self.cleaned_data.get('description', '')
        return bleach.clean(
            description,
            tags=['p', 'b', 'i', 'ul', 'li', 'br'],
            strip=True
        )


class TicketCommentForm(forms.ModelForm):
    class Meta:
        model = TicketComment
        fields = ['body']
        widgets = {
            'body': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Add a comment...'}),
        }

    def clean_body(self):
        body = self.cleaned_data.get('body', '')
        cleaned = bleach.clean(body, tags=[], strip=True)
        if not cleaned.strip():
            raise forms.ValidationError("Comment cannot be empty.")
        return cleaned


class TicketStatusForm(forms.ModelForm):
    """
    Agents use this to update ticket status and priority.
    Separated from TicketForm so customers cannot change
    their own ticket status — a common access control mistake.
    """
    class Meta:
        model = Ticket
        fields = ['status', 'priority', 'assigned_to']
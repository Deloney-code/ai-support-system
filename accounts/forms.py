from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.core.exceptions import ValidationError
from .models import User
import bleach


class SecureRegistrationForm(UserCreationForm):
    """
    Registration form with input sanitization.
    Every field that accepts text is cleaned through bleach
    before it ever touches the database.
    """
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=50, required=True)
    last_name = forms.CharField(max_length=50, required=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name',
                  'last_name', 'password1', 'password2']

    def clean_username(self):
        username = self.cleaned_data.get('username')
        # Strip all HTML — a username should never contain tags
        return bleach.clean(username, tags=[], strip=True)

    def clean_first_name(self):
        name = self.cleaned_data.get('first_name')
        return bleach.clean(name, tags=[], strip=True)

    def clean_last_name(self):
        name = self.cleaned_data.get('last_name')
        return bleach.clean(name, tags=[], strip=True)

    def clean_email(self):
        email = self.cleaned_data.get('email')
        # Check for duplicate emails — Django doesn't do this by default
        if User.objects.filter(email=email).exists():
            raise ValidationError("An account with this email already exists.")
        return email


class SecureLoginForm(AuthenticationForm):
    """
    Login form — extends Django's built-in auth form.
    Rate limiting is applied at the view level, not here.
    """
    username = forms.CharField(
        widget=forms.TextInput(attrs={'autofocus': True})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'})
    )
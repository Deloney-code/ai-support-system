from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    """
    Custom user model — extends Django's built-in auth.
    We add role-based access: agent vs customer.
    """
    ROLE_CHOICES = [
        ('customer', 'Customer'),
        ('agent', 'Agent'),
        ('admin', 'Admin'),
    ]

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='customer'
    )
    phone = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_agent(self):
        return self.role in ['agent', 'admin']

    def is_customer(self):
        return self.role == 'customer'

    def __str__(self):
        return f"{self.username} ({self.role})"

# Create your models here.

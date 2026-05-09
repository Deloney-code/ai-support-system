from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    # Add 'role' to the columns shown in the user list
    list_display = ['username', 'email', 'role', 'is_staff']
    list_filter = ['role', 'is_staff']

    # Add 'role' and 'phone' to the edit form
    fieldsets = UserAdmin.fieldsets + (
        ('Custom Fields', {'fields': ('role', 'phone')}),
    )

# Register your models here.

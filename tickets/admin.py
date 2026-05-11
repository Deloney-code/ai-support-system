from django.contrib import admin
from .models import Ticket, TicketComment

@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'status', 'priority', 'category', 'owner', 'created_at']
    list_filter = ['status', 'priority', 'category']
    search_fields = ['title', 'description', 'owner__username']

@admin.register(TicketComment)
class TicketCommentAdmin(admin.ModelAdmin):
    list_display = ['id', 'ticket', 'author', 'created_at']
    search_fields = ['content', 'author__username']

# Register your models here.

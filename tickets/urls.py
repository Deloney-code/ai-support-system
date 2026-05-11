from django.urls import path
from . import views

app_name = 'tickets'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('create/', views.ticket_create, name='ticket_create'),
    path('<int:pk>/', views.ticket_detail, name='ticket_detail'),
    path('<int:pk>/edit/', views.ticket_edit, name='ticket_edit'),
    path('<int:pk>/close/', views.ticket_close, name='ticket_close'),
    path('<int:pk>/status/', views.ticket_status_update, name='ticket_status_update'),
     # AI endpoints
    path('<int:pk>/ai/polish/', views.ai_polish_reply, name='ai_polish_reply'),
    path('<int:pk>/ai/summarize/', views.ai_summarize, name='ai_summarize'),
    path('<int:pk>/ai/classify/', views.ai_classify, name='ai_classify'),
    path('<int:pk>/ai/auto-resolve/', views.ai_auto_resolve, name='ai_auto_resolve'),
    path('webhook/mailgun/', views.mailgun_webhook, name='mailgun_webhook'),
]

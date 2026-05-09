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
]
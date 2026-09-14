from django.contrib import admin
from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.landing, name='home'),
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls', namespace='accounts')),
    path('tickets/', include('tickets.urls', namespace='tickets')),
]
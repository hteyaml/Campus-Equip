from django.urls import path
from . import views

urlpatterns = [
    # Admin routes
    path('manage/', views.admin_dashboard, name='admin_dashboard'),

    # Basic user routes
    path('portal/', views.user_portal, name='user_portal'),
]
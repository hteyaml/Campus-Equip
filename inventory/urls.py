from django.urls import path
from . import views

urlpatterns = [
    # Admin routes
    path('manage/', views.admin_dashboard, name='admin_dashboard'),
    path('users/', views.user_accounts_view, name='user_accounts'),
    path('equipment/', views.equipment_list_view, name='equipment_list'),
    # Basic user routes
    path('portal/', views.user_portal, name='user_portal'),
    path('my-requests/', views.my_requests, name='my_requests'),
    path('my-portal/', views.my_profile, name='my_profile'),
]
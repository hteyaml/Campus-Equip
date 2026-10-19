from django.urls import path
from . import views

urlpatterns = [
    # Admin routes
    path('manage/', views.admin_dashboard, name='admin_dashboard'),
    path('equipment/', views.equipment_list_view, name='equipment_list'),
    # Basic user routes
    path('portal/', views.user_portal, name='user_portal'),
]
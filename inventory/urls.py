from django.urls import path
from . import views

urlpatterns = [
    # Admin routes
    path('manage/', views.admin_dashboard, name='admin_dashboard'),
    path('users/', views.user_accounts_view, name='user_accounts'),
    path('equipment/', views.equipment_list_view, name='equipment_list'),
    path('loan-reports/', views.loan_reports_view, name='loan_reports'),
    path('overdue-reports/', views.overdue_reports_view, name='overdue_reports'),
    path('audit/', views.audit_log_view, name='audit_log'),
    # Basic user routes
    path('portal/', views.user_portal, name='user_portal'),
    path('my-requests/', views.my_requests, name='my_requests'),
    path('my-profile/', views.my_profile, name='my_profile'),
]
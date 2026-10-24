from django.urls import path
from . import views


urlpatterns = [
    # Admin routes
    path('manage/', views.admin_dashboard, name='admin_dashboard'),
    path('users/', views.user_accounts_view, name='user_accounts'),
    path('manage/users/<int:user_id>/history/', views.user_history, name='user_history'),
    path('manage/users/<int:user_id>/toggle/', views.toggle_user_status, name='toggle_user_status'),

    path('maintenance/', views.maintenance_register_view, name='maintenance_register'),
    path('maintenance/open/', views.open_maintenance, name='open_maintenance'),
    path('maintenance/<int:record_id>/close/', views.close_maintenance, name='close_maintenance'),
    path('reconciliation/', views.inventory_reconciliation_view, name='inventory_reconciliation'),
    path('loan-reports/', views.loan_reports_view, name='loan_reports'),
    path('overdue-reports/', views.overdue_reports_view, name='overdue_reports'),
    path('audit/', views.audit_log_view, name='audit_log'),
    path('settings/', views.operational_settings_view, name='operational_settings'),
    # Basic user routes
    path('portal/', views.user_portal, name='user_portal'),
    path('my-requests/', views.my_requests, name='my_requests'),
    path('my-profile/', views.my_profile, name='my_profile'),
]
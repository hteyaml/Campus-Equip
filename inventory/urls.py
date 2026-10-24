from django.urls import path, include
from . import views

urlpatterns = [

    path('signup/', views.signup, name='signup'),

    # Admin routes
    path('manage/', views.admin_dashboard, name='admin_dashboard'),
    path('users/', views.user_accounts_view, name='user_accounts'),
    path('catalog/', include('inventory.catalog_urls')),
    path('manage/users/<int:user_id>/history/', views.user_history, name='user_history'),
    path('manage/users/<int:user_id>/toggle/', views.toggle_user_status, name='toggle_user_status'),
    path('equipment_list_view/', views.equipment_list_view, name='equipment_list_view'),
    path('review_queue/', views.review_queue, name='review_queue'),
    path('equipment_release/', views.equipment_release, name='equipment_release'),
    path('return_overdue/', views.return_overdue, name='return_overdue'),
    path('maintenance_register/', views.maintenance_register, name='maintenance_register'),
    path('inventory_reconciliation/', views.inventory_reconciliation, name='inventory_reconciliation'),
    path('loan_reports_view/', views.loan_reports_view, name='loan_reports_view'),
    path('overdue-reports/', views.overdue_reports_view, name='overdue_reports'),
    path('audit/', views.audit_log_view, name='audit_log'),
    path('settings/', views.operational_settings, name='operational_settings'),


    # Basic user routes
    path('portal/', views.user_portal, name='user_portal'),
    path('my-requests/', views.my_requests, name='my_requests'),
    path('portal/my-requests/submit/<int:item_id>/', views.submit_borrow_request, name='submit_borrow_request'),
    path('my-profile/', views.my_profile, name='my_profile'),


    path('borrow-request/<int:pk>/update-status/<str:new_status>/', views.update_borrow_status, name='update_borrow_status'),
    path('return-overdue/', views.return_overdue, name='return_overdue'),
    path('review-queue/export/csv/', views.export_queue_csv, name='export_queue_csv'),


]
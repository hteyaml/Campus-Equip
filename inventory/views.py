from django.shortcuts import render
from django.contrib.auth.models import User
from .models import EquipmentUnit, BorrowRequest, Loan, CatalogItem, AuditLog
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from .decorators import admin_required, basic_user_required


@login_required
def role_redirect(request):
    # Check if the user has an active account
    if not request.user.is_active:
        from django.contrib.auth import logout
        logout(request)
        return redirect('login')

        # Route based on the assigned profile role
    if hasattr(request.user, 'profile'):
        if request.user.profile.role == 'ADMIN':
            return redirect('admin_dashboard')
        elif request.user.profile.role == 'BASIC_USER':
            return redirect('user_portal')

    # Fallback if something goes wrong
    return redirect('login')

@admin_required
def admin_dashboard(request):
    # We will pass live database metrics here later
    context = {
        # Original 4 Metrics
        'available_units': EquipmentUnit.objects.filter(inventory_status='Available').count(),
        'pending_requests': BorrowRequest.objects.filter(workflow_status='Pending').count(),
        'active_loans': Loan.objects.count(),  # Or count of non-returned loans
        'overdue_loans': 0,  # Calculated dynamically based on due dates

        # 5 New Metrics
        'maintenance_units': EquipmentUnit.objects.filter(inventory_status='Maintenance').count(),
        'reserved_units': EquipmentUnit.objects.filter(inventory_status='Reserved').count(),
        'active_users': User.objects.filter(profile__role='BASIC_USER', is_active=True).count(),
        'active_catalog_items': CatalogItem.objects.filter(is_archived=False).count(),
        'recent_audits': AuditLog.objects.select_related('actor').order_by('-timestamp')[:5],
    }
    return render(request, 'admin/browse_equipments.html')

def user_accounts_view(request):
    return render(request, 'admin/user_accounts_view.html')

def equipment_list_view(request):
    return render(request, 'admin/equipment_list_view.html')

@basic_user_required
def user_portal(request):
    return render(request, 'portal/browse_equipments.html')

def my_requests(request):
    return render(request, 'portal/my_requests.html')

def my_profile(request):
    return render(request, 'portal/my_profile.html')

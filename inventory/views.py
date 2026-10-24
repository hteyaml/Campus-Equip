from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User
from .models import EquipmentUnit, BorrowRequest, Loan, CatalogItem, AuditLog, Profile
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from .decorators import admin_required, basic_user_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.utils import timezone
from django.db import transaction
from django.db.models import Count, Q
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST
from .models import EquipmentUnit, BorrowRequest, Loan, CatalogItem, AuditLog, Profile, MaintenanceRecord, Category

def signup(request):
    # If the user is already logged in, redirect them away from the signup page
    if request.user.is_authenticated:
        return redirect('role_redirect')

    if request.method == 'POST':
        # Extract data from the HTML form
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        email = request.POST.get('email')
        contact_number = request.POST.get('contact_number')
        username = request.POST.get('username')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')

        # 1. Validation Checks
        if password != confirm_password:
            messages.error(request, 'Passwords do not match.')
            return redirect('signup')

        if User.objects.filter(username=username).exists():
            messages.error(request, 'That username is already taken.')
            return redirect('signup')

        # 2. Create the User (Django securely hashes the password automatically)
        new_user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name
        )

        # 3. Create the Linked Profile (Strictly hardcoded to BASIC_USER)
        Profile.objects.create(
            user=new_user,
            role='BASIC_USER',
            contact_number=contact_number
        )

        # 4. Redirect to login with a success message
        messages.success(request, 'Account created successfully! You can now log in.')
        return redirect('login')

    # If it's a GET request, just render the empty form
    return render(request, 'signup.html')

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
    return render(request, 'admin/dashboard.html')

def user_accounts_view(request):
    # Base query: Fetch ONLY users who have the BASIC_USER role profile
    users_query = User.objects.filter(profile__role='BASIC_USER').order_by('-date_joined')

    # Handle the Search Bar functionality
    search_query = request.GET.get('search')
    if search_query:
        # Search across username, first name, last name, or email
        users_query = users_query.filter(
            Q(username__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query)
        )

    context = {
        'basic_users': users_query,
    }
    return render(request, 'admin/user_accounts_view.html', context)

@admin_required
def user_history(request, user_id):
    # 1. Grabs the specific user based on the ID passed in the URL
    target_user = get_object_or_404(User, id=user_id)

    # 2. Query the SQLite database for all borrow requests owned by this user
    user_requests = BorrowRequest.objects.filter(owner=target_user).order_by('-request_date')

    # We will build this HTML file later; for now, we just pass the user data to it
    context = {
        'target_user': target_user,
        'user_requests': user_requests,
    }
    return render(request, 'admin/user_history.html', context)


@admin_required
def toggle_user_status(request, user_id):
    # Only allow POST requests for security
    if request.method == 'POST':
        target_user = get_object_or_404(User, id=user_id)

        # Flip the current active status (True becomes False, False becomes True)
        target_user.is_active = not target_user.is_active
        target_user.save()

    # Send the admin back to the user directory table
    return redirect('user_accounts')

def loan_reports_view(request):
    return render(request, 'admin/loan_reports_view.html')
def overdue_reports_view(request):
    return render(request, 'admin/overdue_reports_view.html')

def audit_log_view(request):
    return render(request, 'admin/audit_log_view.html')

def operational_settings_view(request):
    return render(request, 'admin/operational_settings_view.html')

@basic_user_required
def user_portal(request):
    return render(request, 'portal/browse_equipments.html')

def my_requests(request):
    return render(request, 'portal/my_requests.html')

def my_profile(request):
    return render(request, 'portal/my_profile.html')


STATUS_KEYS = ['Available', 'Reserved', 'Issued', 'Maintenance', 'Retired']


def _audit(request, action, reference):
    AuditLog.objects.create(actor=request.user, action=action, record_reference=reference)


@admin_required
def maintenance_register_view(request):
    records = MaintenanceRecord.objects.select_related(
        'unit__catalog_item__category', 'responsible_admin'
    ).order_by('-id')

    search = request.GET.get('search', '').strip()
    if search:
        records = records.filter(
            Q(unit__asset_code__icontains=search) | Q(unit__catalog_item__name__icontains=search)
        )
    status = request.GET.get('status', '')
    if status in ('Open', 'Closed'):
        records = records.filter(status=status)
    category = request.GET.get('category', '')
    if category.isdigit():
        records = records.filter(unit__catalog_item__category_id=category)

    page_obj = Paginator(records, 10).get_page(request.GET.get('page'))

    # Summary cards (all records, not just the filtered ones)
    closed = MaintenanceRecord.objects.filter(status='Closed', date_closed__isnull=False)
    days = [(r.date_closed - r.date_opened).days for r in closed]
    stats = {
        'open': MaintenanceRecord.objects.filter(status='Open').count(),
        # closed tickets whose unit went back into service
        'repaired': closed.exclude(unit__inventory_status='Retired').count(),
        'retired': EquipmentUnit.objects.filter(inventory_status='Retired').count(),
        'avg_days': round(sum(days) / len(days), 1) if days else 0,
    }

    context = {
        'records': page_obj,
        'page_obj': page_obj,
        'stats': stats,
        'categories': Category.objects.filter(is_archived=False).order_by('name'),
        # Only Available units may be placed in maintenance
        'units': EquipmentUnit.objects.filter(inventory_status='Available')
                              .select_related('catalog_item').order_by('asset_code'),
        'today': timezone.localdate(),
    }
    return render(request, 'admin/maintenance_register.html', context)


@admin_required
@require_POST
def open_maintenance(request):
    unit_id = request.POST.get('unit', '')
    problem = (request.POST.get('problem') or '').strip()
    if not unit_id.isdigit() or not problem:
        messages.error(request, 'Choose a unit and describe the problem.')
        return redirect('maintenance_register')

    with transaction.atomic():
        unit = get_object_or_404(EquipmentUnit.objects.select_for_update(), pk=unit_id)

        if unit.inventory_status in ('Issued', 'Reserved'):
            messages.error(
                request,
                f'{unit.asset_code} is currently {unit.inventory_status.lower()} and cannot be placed '
                f'in maintenance. Release or cancel the loan first.')
            return redirect('maintenance_register')
        if unit.inventory_status != 'Available':
            messages.error(
                request, f'{unit.asset_code} is {unit.inventory_status.lower()} and cannot be placed in maintenance.')
            return redirect('maintenance_register')

        record = MaintenanceRecord.objects.create(
            unit=unit, problem=problem, responsible_admin=request.user)
        unit.inventory_status = 'Maintenance'
        unit.save(update_fields=['inventory_status'])
        _audit(request, 'Opened maintenance ticket', f'MNT-{record.id} / {unit.asset_code}')

    messages.success(request, f'Ticket #MNT-{record.id} opened for {unit.asset_code}.')
    return redirect('maintenance_register')


@admin_required
@require_POST
def close_maintenance(request, record_id):
    action_taken = (request.POST.get('action_taken') or '').strip()
    outcome = request.POST.get('outcome', '')
    closed_on = parse_date(request.POST.get('closed_on') or '')

    with transaction.atomic():
        record = get_object_or_404(
            MaintenanceRecord.objects.select_for_update().select_related('unit'), pk=record_id)
        unit = record.unit

        error = None
        if record.status != 'Open':
            error = f'Ticket #MNT-{record.id} is already closed.'
        elif not action_taken:
            error = 'Describe the action taken before closing the ticket.'
        elif outcome not in ('repaired', 'retire'):
            error = 'Choose an outcome: repaired or retire.'
        elif closed_on is None:
            error = 'Enter a valid closing date.'
        elif closed_on < record.date_opened:
            error = 'The closing date cannot be earlier than the date opened.'
        elif closed_on > timezone.localdate():
            error = 'The closing date cannot be in the future.'
        if error:
            messages.error(request, error)
            return redirect('maintenance_register')

        record.action_taken = action_taken
        record.date_closed = closed_on
        record.status = 'Closed'
        record.save()

        unit.inventory_status = 'Available' if outcome == 'repaired' else 'Retired'
        unit.save(update_fields=['inventory_status'])
        result = 'unit made Available' if outcome == 'repaired' else 'unit retired'
        _audit(request, f'Closed maintenance ticket ({result})', f'MNT-{record.id} / {unit.asset_code}')

    messages.success(request, f'Ticket #MNT-{record.id} closed: {result}.')
    return redirect('maintenance_register')


@admin_required
def inventory_reconciliation_view(request):
    # Overall counts, straight from the unit records
    agg = EquipmentUnit.objects.aggregate(
        total=Count('id'),
        **{s.lower(): Count('id', filter=Q(inventory_status=s)) for s in STATUS_KEYS})
    counted = sum(agg[s.lower()] for s in STATUS_KEYS)

    # One row per catalog item
    items = CatalogItem.objects.select_related('category').annotate(
        units_total=Count('equipmentunit'),
        **{f'n_{s.lower()}': Count('equipmentunit', filter=Q(equipmentunit__inventory_status=s))
           for s in STATUS_KEYS}
    ).order_by('name')

    search = request.GET.get('search', '').strip()
    if search:
        items = items.filter(name__icontains=search)
    category = request.GET.get('category', '')
    if category.isdigit():
        items = items.filter(category_id=category)

    rows = []
    for it in items:
        row = {'item': it, 'total': it.units_total}
        for s in STATUS_KEYS:
            row[s.lower()] = getattr(it, f'n_{s.lower()}')
        row['balanced'] = sum(row[s.lower()] for s in STATUS_KEYS) == it.units_total
        rows.append(row)

    page_obj = Paginator(rows, 10).get_page(request.GET.get('page'))
    context = {
        'rows': page_obj,
        'page_obj': page_obj,
        'totals': agg,
        'is_balanced': counted == agg['total'],
        'discrepancy': abs(agg['total'] - counted),
        'categories': Category.objects.filter(is_archived=False).order_by('name'),
    }
    return render(request, 'admin/inventory_reconciliation.html', context)

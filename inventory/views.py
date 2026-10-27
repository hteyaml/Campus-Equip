import csv
import calendar

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST
from datetime import timedelta
from django.db.models.functions import ExtractMonth

from .decorators import admin_required, basic_user_required
from .models import (
    AuditLog,
    BorrowRequest,
    CatalogItem,
    Category,
    EquipmentUnit,
    Loan,
    MaintenanceRecord,
    Profile,
    RequestItem,
    ReturnRecord,
    SystemSettings,
    UnitAllocation,
)

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

        # NEW: Check if the Email already exists
        if User.objects.filter(email=email).exists():
            messages.error(request, 'An account with this email address already exists.')
            return redirect('signup')

        # NEW: Check if the Contact Number already exists
        if Profile.objects.filter(contact_number=contact_number).exists():
            messages.error(request, 'This contact number is already registered to another account.')
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
    today = timezone.now().date()
    current_year = today.year

    # Base query for currently deployed items
    issued_requests = BorrowRequest.objects.filter(workflow_status='Issued')

    # 1. Aggregation for Monthly Issued Loans (Current Year)
    # Filter requests for the active year and group them by month (1 to 12)
    monthly_counts = (
        BorrowRequest.objects.filter(
            request_date__year=current_year,
            workflow_status__in=['Issued', 'Returned']
        )
        .annotate(month=ExtractMonth('request_date'))
        .values('month')
        .annotate(count=Count('id'))
    )

    # Map results to full 12-month array ['Jan', 'Feb', ...] and default missing months to 0
    month_map = {item['month']: item['count'] for item in monthly_counts if item['month']}
    monthly_labels = [calendar.month_abbr[m] for m in range(1, 13)]
    monthly_data = [month_map.get(m, 0) for m in range(1, 13)]

    # 2. Aggregation for Equipment Category Usage
    # Count total requested items grouped by category name
    category_qs = (
        RequestItem.objects.values('catalog_item__category__name')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    category_labels = [item['catalog_item__category__name'] or 'Uncategorized' for item in category_qs]
    category_data = [item['count'] for item in category_qs]

    context = {
        # Core Operations
        'available_units': EquipmentUnit.objects.filter(inventory_status='Available').count(),
        'pending_requests': BorrowRequest.objects.filter(workflow_status='Pending').count(),
        'active_loans': issued_requests.filter(desired_return_date__gte=today).count(),
        'overdue_loans': issued_requests.filter(desired_return_date__lt=today).count(),

        # Remaining Secondary Metrics
        'maintenance_units': EquipmentUnit.objects.filter(inventory_status='Maintenance').count(),
        'active_users': User.objects.filter(profile__role='BASIC_USER', is_active=True).count(),

        # Chart Datasets
        'monthly_labels': monthly_labels,
        'monthly_data': monthly_data,
        'category_labels': category_labels,
        'category_data': category_data,

        # Recent Audits
        'recent_audits': AuditLog.objects.select_related('actor').order_by('-timestamp')[:5],
    }
    return render(request, 'admin/admin_dashboard.html', context)

@admin_required
def equipment_list_view(request):
    return render(request, 'admin/equipment_list_view.html')

@admin_required
def review_queue(request):
    borrow_requests = BorrowRequest.objects.all().order_by('-request_date')

    search_query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')
    date_filter = request.GET.get('date', '')

    if search_query:
        borrow_requests = borrow_requests.filter(
            Q(id__icontains=search_query) |
            Q(owner__username__icontains=search_query) |
            Q(item__name__icontains=search_query) |
            Q(purpose__icontains=search_query)
        )

    if status_filter:
        borrow_requests = borrow_requests.filter(workflow_status=status_filter)

    if date_filter:
        borrow_requests = borrow_requests.filter(request_date__date=date_filter)

    pending_count = BorrowRequest.objects.filter(workflow_status='Pending').count()
    approved_count = BorrowRequest.objects.filter(workflow_status='Approved').count()

    context = {
        'borrow_requests': borrow_requests,
        'pending_count': pending_count,
        'approved_count': approved_count,
        'search_query': search_query,
        'status_filter': status_filter,
        'date_filter': date_filter,
    }

    return render(request, 'admin/review_queue.html', context)


@admin_required
def export_queue_csv(request):
    # Kopyahin ang parehong filtering logic mula sa review_queue view
    borrow_requests = BorrowRequest.objects.all().order_by('-request_date')

    search_query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')
    date_filter = request.GET.get('date', '')

    if search_query:
        borrow_requests = borrow_requests.filter(
            Q(id__icontains=search_query) |
            Q(owner__username__icontains=search_query) |
            Q(item__name__icontains=search_query) |
            Q(purpose__icontains=search_query)
        )

    if status_filter:
        borrow_requests = borrow_requests.filter(workflow_status=status_filter)

    if date_filter:
        borrow_requests = borrow_requests.filter(request_date__date=date_filter)

    # I-setup ang HTTP response para sa CSV download
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="review_queue_export.csv"'

    writer = csv.writer(response)
    # Sulatan ng column headers ang CSV
    writer.writerow(
        ['Request ID', 'Borrower', 'Item Request', 'Category', 'Request Date', 'Anticipated Return', 'Status'])

    # Ilagay ang bawat row ng data mula sa database
    for req in borrow_requests:
        borrower_name = req.owner.username if req.owner else f"User #{req.owner_id}"
        item_name = req.item.name if req.item else "No item linked"
        category_name = req.item.category.name if (req.item and req.item.category) else ""

        writer.writerow([
            f"#REQ-{req.id}",
            borrower_name,
            item_name,
            category_name,
            req.request_date.strftime("%Y-%m-%d %H:%M") if req.request_date else "",
            req.desired_return_date.strftime("%Y-%m-%d") if req.desired_return_date else "",
            req.workflow_status
        ])

    return response


@admin_required
def update_borrow_status(request, pk, new_status):
    borrow_req = get_object_or_404(BorrowRequest, pk=pk)

    # Block actions on terminal states
    terminal_statuses = ['Returned', 'Rejected', 'Cancelled']
    if borrow_req.workflow_status in terminal_statuses:
        messages.error(request,
                       f"Action denied: You cannot change the status of a {borrow_req.workflow_status} request.")
        return redirect(request.META.get('HTTP_REFERER', 'review_queue'))

    valid_statuses = ['Approved', 'Rejected', 'Issued', 'Returned', 'Cancelled']

    if new_status in valid_statuses:
        # 1. APPROVE: Reserve the units
        if new_status == 'Approved' and borrow_req.workflow_status != 'Approved':
            for req_item in borrow_req.requestitem_set.all():
                if not UnitAllocation.objects.filter(request_item=req_item, is_cancelled=False).exists():
                    available_units = EquipmentUnit.objects.filter(
                        catalog_item=req_item.catalog_item,
                        inventory_status='Available'
                    )[:req_item.quantity]

                    for unit in available_units:
                        UnitAllocation.objects.create(request_item=req_item, unit=unit)
                        unit.inventory_status = 'Reserved'
                        unit.save()

        # 2. ISSUE: Create Loan and mark reserved units as Issued
        elif new_status == 'Issued' and borrow_req.workflow_status != 'Issued':
            loan, created = Loan.objects.get_or_create(
                borrow_request=borrow_req,
                defaults={
                    'issue_actor': request.user,
                    'due_date': borrow_req.desired_return_date,
                    'issue_date': timezone.now()
                }
            )
            allocations = UnitAllocation.objects.filter(request_item__borrow_request=borrow_req, is_cancelled=False)
            for alloc in allocations:
                unit = alloc.unit
                unit.inventory_status = 'Issued'
                unit.save()

        # 3. RETURN: Create ReturnRecord and free units back to Available
        elif new_status == 'Returned' and borrow_req.workflow_status != 'Returned':
            loan = Loan.objects.filter(borrow_request=borrow_req).first()
            if loan:
                allocations = UnitAllocation.objects.filter(request_item__borrow_request=borrow_req, is_cancelled=False)
                for alloc in allocations:
                    unit = alloc.unit
                    ReturnRecord.objects.get_or_create(loan=loan, unit=unit)
                    unit.inventory_status = 'Available'
                    unit.save()

        # 4. CANCEL/REJECT: Free up reserved units
        elif new_status in ['Cancelled', 'Rejected']:
            allocations = UnitAllocation.objects.filter(request_item__borrow_request=borrow_req, is_cancelled=False)
            for alloc in allocations:
                unit = alloc.unit
                unit.inventory_status = 'Available'
                unit.save()
                alloc.is_cancelled = True
                alloc.save()

        # --- NEW LOGIC: Record the action in the Audit Log ---
        AuditLog.objects.create(
            actor=request.user,
            action=f"Updated request status to {new_status}",
            record_reference=f"#REQ-{borrow_req.id}"
        )

        # Update the main request status
        borrow_req.workflow_status = new_status
        borrow_req.save()

        messages.success(request, f"Request #REQ-{borrow_req.id} successfully marked as {new_status}.")

    return redirect(request.META.get('HTTP_REFERER', 'review_queue'))

@admin_required
def equipment_release(request):
    requests_query = BorrowRequest.objects.filter(
        workflow_status__in=['Approved', 'Issued']
    ).order_by('-request_date')

    # Search at Filter parameters
    search_query = request.GET.get('q', '')

    if search_query:
        requests_query = requests_query.filter(
            Q(id__icontains=search_query.replace('#REQ-', '')) |
            Q(owner__username__icontains=search_query) |
            Q(item__name__icontains=search_query)
        )


    ready_count = BorrowRequest.objects.filter(workflow_status='Approved').count()
    dispatched_count = BorrowRequest.objects.filter(workflow_status='Issued').count()
    tag_verification_count = BorrowRequest.objects.filter(
        workflow_status='Pending').count()

    context = {
        'borrow_requests': requests_query,
        'ready_count': ready_count,
        'dispatched_count': dispatched_count,
        'tag_verification_count': tag_verification_count,
        'search_query': search_query,
    }

    return render(request, 'admin/equipment_release.html', context)

@admin_required
def return_overdue(request):
    today = timezone.now().date()

    # Kunin ang lahat ng kagamitang nailabas na (Issued)
    issued_requests = BorrowRequest.objects.filter(workflow_status='Issued')

    # 1. Active Deployments: Issued status at HINDI PA overdue (desired_return_date >= today)
    active_loans = issued_requests.filter(desired_return_date__gte=today).order_by('desired_return_date')

    # 2. Overdue Delinquencies: Issued status at OVERDUE NA (desired_return_date < today)
    overdue_loans = issued_requests.filter(desired_return_date__lt=today).order_by('desired_return_date')

    # Metrics computation
    active_count = active_loans.count()
    overdue_count = overdue_loans.count()

    # Optional counter para sa maintenance/returned routing
    returned_count = BorrowRequest.objects.filter(workflow_status='Returned').count()

    context = {
        'active_loans': active_loans,
        'overdue_loans': overdue_loans,
        'active_count': active_count,
        'overdue_count': overdue_count,
        'returned_count': returned_count,
        'today': today,
    }

    return render(request, 'admin/return_overdue.html', context)

@admin_required
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

@admin_required
def loan_reports_view(request):
    return render(request, 'admin/loan_reports_view.html')

@admin_required
def overdue_reports_view(request):
    return render(request, 'admin/overdue_reports_view.html')

@admin_required
def audit_log_view(request):
    # Fetch all logs, ordering by newest first
    logs_query = AuditLog.objects.select_related('actor').order_by('-timestamp')

    # Handle Search Bar
    search_query = request.GET.get('search', '').strip()
    if search_query:
        logs_query = logs_query.filter(
            Q(actor__username__icontains=search_query) |
            Q(actor__first_name__icontains=search_query) |
            Q(actor__last_name__icontains=search_query) |
            Q(action__icontains=search_query) |
            Q(record_reference__icontains=search_query)
        )

    # Paginate results (15 records per page)
    paginator = Paginator(logs_query, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'logs': page_obj,
        'search_query': search_query,
    }
    return render(request, 'admin/audit_log_view.html', context)

@admin_required
def operational_settings(request):
    # Fetch the global settings row, or create it if it doesn't exist yet
    current_settings, created = SystemSettings.objects.get_or_create(pk=1)

    if request.method == 'POST':
        # Retrieve the updated integer values from the form
        max_duration = request.POST.get('max_loan_duration', 7)
        max_qty = request.POST.get('max_quantity', 3)

        # Save them to the database
        current_settings.max_loan_duration_days = int(max_duration)
        current_settings.max_quantity_per_item = int(max_qty)
        current_settings.save()

        messages.success(request, "Operational settings have been updated successfully.")
        return redirect('operational_settings') # Ensure this matches your urls.py name

    context = {
        'current_settings': current_settings
    }
    return render(request, 'admin/operational_settings_view.html', context)


@basic_user_required
def user_portal(request):
    search_query = request.GET.get('search', '').strip()
    category_filter = request.GET.get('category', '').strip()

    items = CatalogItem.objects.annotate(
        total_units=Count('equipmentunit', distinct=True),
        available_units=Count(
            'equipmentunit',
            filter=Q(equipmentunit__inventory_status='Available'),
            distinct=True
        )
    ).order_by('name')

    # UPDATED LOGIC: Added Category Name to the text search
    if search_query:
        items = items.filter(
            Q(name__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(category__name__icontains=search_query)  # <-- Added this line
        )

    if category_filter:
        items = items.filter(category__name=category_filter)

    categories = CatalogItem.objects.values_list('category__name', flat=True).distinct()

    # --- NEW LOGIC: Calculate date limits for the Request Modal ---
    settings = SystemSettings.objects.first()
    max_days = settings.max_loan_duration_days if settings else 7
    max_qty = settings.max_quantity_per_item if settings else 3

    today = timezone.localdate()
    min_date = today.strftime('%Y-%m-%d')
    max_date = (today + timedelta(days=max_days)).strftime('%Y-%m-%d')

    context = {
        'catalog_items': items,
        'categories': categories,
        'selected_category': category_filter,
        'search_query': search_query,
        'min_date': min_date,
        'max_date': max_date,
        'max_days': max_days,
        'max_qty': max_qty,
    }
    return render(request, 'portal/browse_equipments.html', context)


@basic_user_required
def my_requests(request):
    # Fetch only the requests made by the currently logged-in student
    student_requests = BorrowRequest.objects.filter(owner=request.user).order_by('-id')

    # Calculate overdue status for each request
    today = timezone.localdate()
    for req in student_requests:
        req.is_overdue = (
            req.workflow_status == 'Issued' and
            req.desired_return_date is not None and
            req.desired_return_date < today
        )

    context = {
        'requests': student_requests,
    }

    return render(request, 'portal/my_requests.html', context)



@basic_user_required
def my_profile(request):
    user = request.user
    profile, created = Profile.objects.get_or_create(user=user)

    if request.method == 'POST':

        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        contact_number = request.POST.get('contact_number', '').strip()

        user.first_name = first_name
        user.last_name = last_name
        user.save()

        profile.contact_number = contact_number
        profile.save()

        messages.success(request, "Your profile has been updated successfully.")
        return redirect('my_profile')

    return render(request, 'portal/my_profile.html', {
        'user': user,
        'profile': profile,
    })

@basic_user_required
def submit_borrow_request(request, item_id):
    """Handles the creation of a new borrow request from the student portal."""
    if request.method == 'POST':
        catalog_item = get_object_or_404(CatalogItem, id=item_id)

        # Get data from the modal form
        quantity = int(request.POST.get('quantity', 1))
        purpose = request.POST.get('purpose', '').strip()

        # ADDED: Get the return date from the form
        desired_return_date = request.POST.get('desired_return_date')

        # Create the parent Borrow Request
        borrow_req = BorrowRequest.objects.create(
            owner=request.user,
            item=catalog_item,
            desired_return_date=desired_return_date,  # ADDED: Save to database
            purpose=purpose,
            workflow_status='Pending'
        )

        # Create the specific Item entry linked to the request
        RequestItem.objects.create(
            borrow_request=borrow_req,
            catalog_item=catalog_item,
            quantity=quantity
        )

        messages.success(request, f"Your request for {quantity}x {catalog_item.name} has been submitted for review.")

    return redirect('user_portal')


# --- Loan & Overdue Reports backend ---
from .report_views import loan_reports_view, overdue_reports_view  # noqa: E402,F401


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

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User
from .models import EquipmentUnit, BorrowRequest, Loan, CatalogItem, AuditLog, Profile, RequestItem
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from .decorators import admin_required, basic_user_required
from django.contrib import messages


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
    return render(request, 'admin/admin_dashboard.html')

@admin_required
def equipment_list_view(request):
    return render(request, 'admin/equipment_list_view.html')

@admin_required
def review_queue(request):
    return render(request, 'admin/review_queue.html')

@admin_required
def equipment_release(request):
    return render(request, 'admin/equipment_release.html')

@admin_required
def return_overdue(request):
    return render(request, 'admin/return_overdue.html')

@admin_required
def maintenance_register(request):
    return render(request, 'admin/maintenance_register.html')

@admin_required
def inventory_reconciliation(request):
    return render(request, 'admin/inventory_reconciliation.html')

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
    return render(request, 'admin/audit_log_view.html')

@admin_required
def operational_settings_view(request):
    return render(request, 'admin/operational_settings_view.html')



@basic_user_required
def user_portal(request):
    """
    Displays equipment catalog for student browsing with search,
    category filtering, and real-time availability counts.
    """
    search_query = request.GET.get('search', '').strip()
    category_filter = request.GET.get('category', '').strip()

    # Annotate total physical units per catalog item
    items = CatalogItem.objects.annotate(
        total_units=Count('equipmentunit')
    ).order_by('name')

    # Apply search filter
    if search_query:
        items = items.filter(
            Q(name__icontains=search_query) |
            Q(description__icontains=search_query)
        )

    # Apply category filter
    if category_filter:
        items = items.filter(category_id=category_filter)

    # Safely compute available units for each catalog item
    for item in items:
        # Access the related equipment units manager
        units_manager = getattr(item, 'equipmentunit', None) or getattr(item, 'equipmentunit_set', None)
        if units_manager:
            try:
                item.available_units = units_manager.filter(status='AVAILABLE').count()
            except Exception:
                # Fallback if status uses a foreign key / lookup
                try:
                    item.available_units = units_manager.filter(status__name='AVAILABLE').count()
                except Exception:
                    item.available_units = item.total_units
        else:
            item.available_units = 0

    # Fetch unique categories for the filter dropdown
    categories = CatalogItem.objects.values_list('category__name', flat=True).distinct()

    context = {
        'catalog_items': items,
        'categories': categories,
        'selected_category': category_filter,
        'search_query': search_query,
    }
    return render(request, 'portal/browse_equipments.html', context)

def my_requests(request):
    return render(request, 'portal/my_requests.html')


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
            purpose=purpose,
            desired_return_date=desired_return_date,  # ADDED: Save to database
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

def my_profile(request):
    return render(request, 'portal/my_profile.html')



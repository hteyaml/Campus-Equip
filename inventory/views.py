from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User
from .models import EquipmentUnit, BorrowRequest, Loan, CatalogItem, AuditLog, Profile
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Q
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

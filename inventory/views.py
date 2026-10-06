from django.shortcuts import render

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
    return render(request, 'admin/dashboard.html')

@basic_user_required
def user_portal(request):
    # We will pass the user's request history here later
    return render(request, 'portal/dashboard.html')

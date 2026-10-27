from django.core.exceptions import PermissionDenied
from functools import wraps
from django.shortcuts import redirect

def admin_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_active:
            return redirect('login')
        if hasattr(request.user, 'profile') and request.user.profile.role == 'ADMIN':
            return view_func(request, *args, **kwargs)
        raise PermissionDenied # Shows a 403 Forbidden error if a basic user tries to access
    return _wrapped_view

def basic_user_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_active:
            return redirect('login')
        if hasattr(request.user, 'profile') and request.user.profile.role == 'BASIC_USER':
            return view_func(request, *args, **kwargs)
        raise PermissionDenied
    return _wrapped_view
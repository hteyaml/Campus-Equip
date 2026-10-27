from django.core.exceptions import PermissionDenied
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.views.decorators.cache import never_cache


def basic_user_required(view_func):
    @wraps(view_func)
    @never_cache  # <-- ADD THIS HERE
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, "Please log in to access this page.")
            return redirect('login')

        # (Keep whatever role-checking logic you already have here)

        return view_func(request, *args, **kwargs)

    return _wrapped_view


def admin_required(view_func):
    @wraps(view_func)
    @never_cache  # <-- ADD THIS HERE TOO
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, "Please log in to access this page.")
            return redirect('login')

        # (Keep whatever admin role-checking logic you already have here)

        return view_func(request, *args, **kwargs)

    return _wrapped_view
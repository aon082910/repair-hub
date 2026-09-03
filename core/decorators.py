from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def _staff_check(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied("This page is only available to shop staff accounts.")
        return view_func(request, *args, **kwargs)
    return wrapper


def staff_required(view_func):
    """Staff-only view: anonymous users are sent to login; logged-in
    non-staff (e.g. customer/technician accounts) get a 403 instead of a
    redirect loop."""
    return login_required(_staff_check(view_func))


def _staff_or_technician_check(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_staff or hasattr(request.user, "technician_profile")):
            raise PermissionDenied("This page requires a staff or technician account.")
        return view_func(request, *args, **kwargs)
    return wrapper


def staff_or_technician_required(view_func):
    """Reference/lookup pages (vehicles, guides, DTC codes, wiring diagrams)
    that both staff and technicians need while working, but customers
    should not see."""
    return login_required(_staff_or_technician_check(view_func))


def _technician_check(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not hasattr(request.user, "technician_profile"):
            raise PermissionDenied("This page is only available to technician accounts.")
        return view_func(request, *args, **kwargs)
    return wrapper


def technician_required(view_func):
    return login_required(_technician_check(view_func))

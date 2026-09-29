from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .models import User


def roles_required(*roles):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if request.user.is_superuser or request.user.role in roles:
                return view_func(request, *args, **kwargs)
            raise PermissionDenied

        return wrapped
    return decorator


admin_required = roles_required(User.Role.ADMIN)
hr_required = roles_required(User.Role.ADMIN, User.Role.HR)

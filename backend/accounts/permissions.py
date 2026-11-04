"""Role-based DRF permissions. Every endpoint lists its allowed roles explicitly.

ADMIN is NOT implicitly allowed anywhere (decision K23) — list it where it is needed.
"""

from rest_framework.permissions import BasePermission

from . import errors
from .roles import RoleCode


def roles_permission(*codes: RoleCode) -> type[BasePermission]:
    """Build a permission class that allows authenticated users with one of `codes`."""
    allowed = frozenset(str(c) for c in codes)

    class HasRole(BasePermission):
        message = errors.PERMISSION_DENIED
        allowed_roles = allowed

        def has_permission(self, request, view) -> bool:
            user = request.user
            return bool(
                user and user.is_authenticated and user.is_active and user.role.code in allowed
            )

    HasRole.__name__ = "HasRole_" + "_".join(sorted(allowed))
    return HasRole

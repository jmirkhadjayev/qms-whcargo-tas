from typing import Any

from .models import AuditAction, AuditLog


def client_ip(request: Any) -> str | None:
    """REMOTE_ADDR only: X-Forwarded-For is client-controlled unless a trusted proxy sets it."""
    return request.META.get("REMOTE_ADDR") if request is not None else None


def log(
    action: AuditAction | str,
    entity: str,
    entity_id: int | None = None,
    user: Any = None,
    old_value: Any = None,
    new_value: Any = None,
    ip: str | None = None,
) -> AuditLog:
    """Append an audit record. `user` may be None (system, anonymous, failed login)."""
    if user is not None and not getattr(user, "is_authenticated", False):
        user = None
    return AuditLog.objects.create(
        user=user,
        action=str(action),
        entity=entity,
        entity_id=entity_id,
        old_value=old_value,
        new_value=new_value,
        ip_address=ip,
    )

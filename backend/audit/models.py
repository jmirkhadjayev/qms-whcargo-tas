from django.conf import settings
from django.db import models

from .append_only import AppendOnlyModel


class AuditAction(models.TextChoices):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    LOGIN = "LOGIN"
    LOGIN_FAILED = "LOGIN_FAILED"
    EXPORT = "EXPORT"
    TRANSITION = "TRANSITION"
    PERMIT_REJECTED = "PERMIT_REJECTED"
    REOPEN = "REOPEN"
    PRINT = "PRINT"
    REPRINT = "REPRINT"


class AuditLog(AppendOnlyModel):
    """Who did what. Rows are only ever inserted (domain rule 3)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    action = models.CharField(max_length=30, choices=AuditAction.choices)
    entity = models.CharField(max_length=100)
    entity_id = models.BigIntegerField(null=True, blank=True)
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_log"
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["entity", "entity_id"], name="ix_audit_entity"),
            models.Index(fields=["user", "created_at"], name="ix_audit_user_time"),
            models.Index(fields=["action", "created_at"], name="ix_audit_action_time"),
        ]

    def __str__(self) -> str:
        return f"{self.action} {self.entity}#{self.entity_id}"

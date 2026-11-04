from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class WarehouseTaskStatus(models.TextChoices):
    NEW = "NEW"
    IN_PROGRESS = "IN_PROGRESS"
    READY = "READY"
    HANDED_OVER = "HANDED_OVER"
    PROBLEM = "PROBLEM"


class WarehouseTask(models.Model):
    request = models.ForeignKey(
        "cargo_queue.QueueRequest", on_delete=models.PROTECT, related_name="warehouse_tasks"
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    storage_location = models.CharField(max_length=100, blank=True)
    status = models.CharField(
        max_length=15, choices=WarehouseTaskStatus.choices, default=WarehouseTaskStatus.NEW
    )
    created_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    handed_over_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "warehouse_tasks"
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=WarehouseTaskStatus.values), name="ck_wtask_status"
            )
        ]
        indexes = [models.Index(fields=["status", "created_at"], name="ix_wtask_status_time")]

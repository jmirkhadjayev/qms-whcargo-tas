from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class ExceptionKind(models.TextChoices):
    MISSING = "MISSING"  # cargo not found
    DAMAGE = "DAMAGE"  # shikast
    SHORTAGE = "SHORTAGE"  # kamomad
    MISMATCH = "MISMATCH"  # data discrepancy (tafovut)
    PARTIAL = "PARTIAL"
    NO_SHOW = "NO_SHOW"  # kelmaslik
    CHECKPOINT = "CHECKPOINT"  # discrepancy found at the checkpoint


class ExceptionRecord(models.Model):
    request = models.ForeignKey(
        "cargo_queue.QueueRequest", on_delete=models.PROTECT, related_name="exceptions"
    )
    kind = models.CharField(max_length=15, choices=ExceptionKind.choices)
    pieces_affected = models.PositiveIntegerField(default=0)
    description = models.TextField(blank=True)
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )  # null: system
    reported_at = models.DateTimeField(default=timezone.now)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution = models.TextField(blank=True)

    class Meta:
        db_table = "exceptions"
        ordering = ["reported_at"]
        constraints = [
            models.CheckConstraint(condition=Q(kind__in=ExceptionKind.values), name="ck_exc_kind")
        ]
        indexes = [
            models.Index(
                fields=["request"],
                condition=Q(resolved_at__isnull=True),
                name="ix_exc_open_by_request",
            )
        ]

    @property
    def is_open(self) -> bool:
        return self.resolved_at is None

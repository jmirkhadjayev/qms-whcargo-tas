from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class CheckpointResult(models.TextChoices):
    APPROVED = "APPROVED"
    HELD = "HELD"


class CheckpointPass(models.Model):
    request = models.ForeignKey(
        "cargo_queue.QueueRequest", on_delete=models.PROTECT, related_name="checkpoint_passes"
    )
    officer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    scanned_at = models.DateTimeField(default=timezone.now)
    plate_observed = models.CharField(max_length=20, blank=True)
    result = models.CharField(max_length=10, choices=CheckpointResult.choices)
    exit_confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "checkpoint_passes"
        ordering = ["scanned_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(result__in=CheckpointResult.values), name="ck_cp_result"
            )
        ]

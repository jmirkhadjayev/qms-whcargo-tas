import secrets
from typing import Any

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class DockState(models.TextChoices):
    FREE = "FREE"
    BUSY = "BUSY"
    MAINTENANCE = "MAINTENANCE"


class Dock(models.Model):
    code = models.CharField(max_length=10, unique=True)  # D-01
    name = models.CharField(max_length=100)
    state = models.CharField(max_length=15, choices=DockState.choices, default=DockState.FREE)
    is_active = models.BooleanField(default=True)
    # Staff readiness (decision K27).
    current_agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    agent_ready_at = models.DateTimeField(null=True, blank=True)
    categories: "models.ManyToManyField[Any, Any]" = models.ManyToManyField(
        "cargo_queue.CargoCategory", through="DockCategory", related_name="docks"
    )

    class Meta:
        db_table = "docks"
        ordering = ["code"]
        constraints = [
            models.CheckConstraint(condition=Q(state__in=DockState.values), name="ck_dock_state")
        ]

    def __str__(self) -> str:
        return self.code


class DockCategory(models.Model):
    """Which cargo categories a dock may handle (surrogate id + unique pair, no composite PK)."""

    dock = models.ForeignKey(Dock, on_delete=models.CASCADE, related_name="dock_categories")
    category = models.ForeignKey(
        "cargo_queue.CargoCategory", on_delete=models.CASCADE, related_name="dock_categories"
    )

    class Meta:
        db_table = "dock_categories"
        constraints = [
            models.UniqueConstraint(fields=["dock", "category"], name="uq_dock_category")
        ]


class ScreenKind(models.TextChoices):
    DOCK_LED = "DOCK_LED"
    HALL = "HALL"


class ScreenProtocol(models.TextChoices):
    BROWSER = "BROWSER"
    TCP = "TCP"
    RS485 = "RS485"


def new_screen_token() -> str:
    return secrets.token_urlsafe(24)


class DisplayScreen(models.Model):
    dock = models.ForeignKey(
        Dock, null=True, blank=True, on_delete=models.CASCADE, related_name="screens"
    )  # null: hall screen
    kind = models.CharField(max_length=10, choices=ScreenKind.choices)
    address = models.CharField(max_length=100, blank=True)
    protocol = models.CharField(
        max_length=10, choices=ScreenProtocol.choices, default=ScreenProtocol.BROWSER
    )
    last_seen_at = models.DateTimeField(null=True, blank=True)
    # Secret that lets a kiosk browser open its own screen without logging in.
    token = models.CharField(max_length=64, unique=True, default=new_screen_token)

    class Meta:
        db_table = "display_screens"

    def __str__(self) -> str:
        return f"{self.kind} {self.dock or 'hall'}"


class CallOutcome(models.TextChoices):
    ARRIVED = "ARRIVED"
    NO_SHOW = "NO_SHOW"
    PENDING = "PENDING"


class CallEvent(models.Model):
    request = models.ForeignKey(
        "cargo_queue.QueueRequest", on_delete=models.PROTECT, related_name="call_events"
    )
    dock = models.ForeignKey(Dock, on_delete=models.PROTECT, related_name="call_events")
    attempt_no = models.PositiveSmallIntegerField(default=1)  # 1 first call, 2+ recalls
    called_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )  # null: system
    called_at = models.DateTimeField(default=timezone.now)
    arrived_at = models.DateTimeField(null=True, blank=True)
    outcome = models.CharField(
        max_length=10, choices=CallOutcome.choices, default=CallOutcome.PENDING
    )

    class Meta:
        db_table = "call_events"
        ordering = ["called_at"]
        constraints = [
            models.CheckConstraint(condition=Q(attempt_no__gte=1), name="ck_call_attempt_pos"),
            models.CheckConstraint(
                condition=Q(outcome__in=CallOutcome.values), name="ck_call_outcome"
            ),
        ]


class ReleaseOperation(models.Model):
    request = models.ForeignKey(
        "cargo_queue.QueueRequest", on_delete=models.PROTECT, related_name="release_operations"
    )
    dock = models.ForeignKey(Dock, on_delete=models.PROTECT, related_name="release_operations")
    agent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    pieces_released = models.PositiveIntegerField(default=0)
    weight_released_kg = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        db_table = "release_operations"
        constraints = [
            # sum(pieces_released) <= pieces_total is enforced by a DB trigger (migration 0002).
            models.CheckConstraint(
                condition=Q(pieces_released__gte=0), name="ck_pieces_released_nonneg"
            ),
            models.CheckConstraint(
                condition=Q(weight_released_kg__gte=0), name="ck_weight_released_nonneg"
            ),
        ]

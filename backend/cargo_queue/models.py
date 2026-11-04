from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from audit.append_only import AppendOnlyModel

from .statuses import INACTIVE_STATUSES, RequestStatus


class StatusChangeNotAllowed(Exception):
    """`status` may only change through cargo_queue.services.state_machine (domain rule 2)."""


class CargoCategory(models.Model):
    code = models.CharField(max_length=10, unique=True)  # GEN, OVZ, DGR, PER, VAL
    name = models.CharField(max_length=100)
    special_handling = models.BooleanField(default=False)
    default_priority = models.SmallIntegerField(default=0)

    class Meta:
        db_table = "cargo_categories"
        ordering = ["id"]

    def __str__(self) -> str:
        return self.code


class Shift(models.Model):
    name = models.CharField(max_length=50)
    starts_at = models.TimeField()
    ends_at = models.TimeField()  # may be earlier than starts_at: the shift crosses midnight

    class Meta:
        db_table = "shifts"
        ordering = ["starts_at"]

    def __str__(self) -> str:
        return self.name


class Consignee(models.Model):
    name = models.CharField(max_length=255)
    tin = models.CharField(max_length=20, null=True, blank=True)  # STIR; null for individuals
    representative_name = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "consignees"
        constraints = [
            models.UniqueConstraint(
                fields=["tin"], condition=Q(tin__isnull=False), name="uq_consignee_tin"
            )
        ]

    def __str__(self) -> str:
        return self.name


class PermitStatus(models.TextChoices):
    VERIFIED = "VERIFIED"
    INVALID = "INVALID"
    REVOKED = "REVOKED"


class PermitSource(models.TextChoices):
    AWERY = "AWERY"
    MANUAL = "MANUAL"
    MOCK = "MOCK"


class ReleasePermit(models.Model):
    awb_number = models.CharField(max_length=20, db_index=True)
    permit_number = models.CharField(max_length=100)
    source = models.CharField(max_length=10, choices=PermitSource.choices)
    status = models.CharField(max_length=10, choices=PermitStatus.choices)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "release_permits"
        constraints = [
            models.UniqueConstraint(
                fields=["awb_number", "permit_number"], name="uq_permit_awb_number"
            ),
            models.CheckConstraint(
                condition=Q(status__in=PermitStatus.values), name="ck_permit_status"
            ),
            models.CheckConstraint(
                condition=Q(source__in=PermitSource.values), name="ck_permit_source"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.awb_number} / {self.permit_number} ({self.status})"


class QueueRequestQuerySet(models.QuerySet):
    def update(self, **kwargs: Any):
        if "status" in kwargs:
            raise StatusChangeNotAllowed("status faqat holatlar mashinasi orqali o‘zgaradi.")
        return super().update(**kwargs)

    def bulk_update(self, objs, fields, *args: Any, **kwargs: Any):
        if "status" in fields:
            raise StatusChangeNotAllowed("status faqat holatlar mashinasi orqali o‘zgaradi.")
        return super().bulk_update(objs, fields, *args, **kwargs)

    def active(self):
        return self.exclude(status__in=INACTIVE_STATUSES)


class QueueRequest(models.Model):  # type: ignore[django-manager-missing,unused-ignore]
    queue_date = models.DateField()
    queue_number = models.PositiveIntegerField()
    awb_number = models.CharField(max_length=20)
    consignee = models.ForeignKey(Consignee, on_delete=models.PROTECT, related_name="requests")
    permit = models.ForeignKey(ReleasePermit, on_delete=models.PROTECT, related_name="requests")
    category = models.ForeignKey(CargoCategory, on_delete=models.PROTECT, related_name="requests")
    shift = models.ForeignKey(Shift, on_delete=models.PROTECT, related_name="requests")
    dock = models.ForeignKey(
        "docks.Dock", null=True, blank=True, on_delete=models.PROTECT, related_name="requests"
    )
    pieces_total = models.PositiveIntegerField()
    weight_kg = models.DecimalField(max_digits=10, decimal_places=2)
    vehicle_plate = models.CharField(max_length=20, blank=True)
    sms_phone = models.CharField(max_length=20)
    representative_name = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=30, choices=RequestStatus.choices, default=RequestStatus.REGISTERED
    )
    priority = models.SmallIntegerField(default=0)
    sort_at = models.DateTimeField(default=timezone.now)
    qr_token = models.CharField(max_length=64, unique=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    registered_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)

    objects = QueueRequestQuerySet.as_manager()

    # Set by the state machine around its own save(); everyone else cannot change `status`.
    _status_change_allowed = False
    _loaded_status: str | None = None

    class Meta:
        db_table = "queue_requests"
        ordering = ["-queue_date", "-queue_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["queue_date", "queue_number"], name="uq_queue_date_number"
            ),
            # One active request per AWB and per permit (decision K19).
            models.UniqueConstraint(
                fields=["awb_number"],
                condition=~Q(status__in=INACTIVE_STATUSES),
                name="uq_active_request_per_awb",
            ),
            models.UniqueConstraint(
                fields=["permit"],
                condition=~Q(status__in=INACTIVE_STATUSES),
                name="uq_active_request_per_permit",
            ),
            models.CheckConstraint(condition=Q(pieces_total__gt=0), name="ck_pieces_total_pos"),
            models.CheckConstraint(condition=Q(weight_kg__gt=0), name="ck_weight_pos"),
            models.CheckConstraint(condition=Q(queue_number__gt=0), name="ck_queue_number_pos"),
            models.CheckConstraint(condition=Q(priority__gte=0), name="ck_priority_nonneg"),
            models.CheckConstraint(
                condition=Q(status__in=RequestStatus.values), name="ck_request_status"
            ),
        ]
        indexes = [
            models.Index(fields=["queue_date", "status"], name="ix_req_date_status"),
            models.Index(fields=["status"], name="ix_req_status"),
            models.Index(fields=["dock", "status"], name="ix_req_dock_status"),
            models.Index(fields=["registered_at"], name="ix_req_registered_at"),
            # The live queue: only active requests, ordered by priority then sort_at (K8).
            models.Index(
                fields=["-priority", "sort_at"],
                condition=~Q(status__in=INACTIVE_STATUSES),
                name="ix_req_active_order",
            ),
        ]

    def __str__(self) -> str:
        return f"№{self.queue_number} {self.awb_number} [{self.status}]"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if (
            not self._state.adding
            and self._loaded_status is not None
            and self.status != self._loaded_status
            and not self._status_change_allowed
        ):
            raise StatusChangeNotAllowed("status faqat holatlar mashinasi orqali o‘zgaradi.")
        super().save(*args, **kwargs)
        self._loaded_status = self.status

    def delete(self, *args: Any, **kwargs: Any):
        raise StatusChangeNotAllowed("Arizalar o‘chirilmaydi — CANCELLED holatiga o‘tkazing.")

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        instance._loaded_status = instance.__dict__.get("status")
        return instance


class QueueCounter(models.Model):
    """Per-day counter behind queue numbers (decision K7)."""

    queue_date = models.DateField(primary_key=True)
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "queue_counters"


class Ticket(models.Model):
    request = models.ForeignKey(QueueRequest, on_delete=models.PROTECT, related_name="tickets")
    printed_at = models.DateTimeField(default=timezone.now)
    printed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    is_reprint = models.BooleanField(default=False)

    class Meta:
        db_table = "tickets"
        ordering = ["printed_at"]


class RequestStatusHistory(AppendOnlyModel):
    request = models.ForeignKey(QueueRequest, on_delete=models.PROTECT, related_name="history")
    from_status = models.CharField(max_length=30, null=True, blank=True)  # null: creation
    to_status = models.CharField(max_length=30)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )  # null means the system
    reason = models.TextField(blank=True)
    changed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "request_status_history"
        ordering = ["changed_at", "id"]
        indexes = [
            models.Index(fields=["request", "changed_at"], name="ix_hist_request_time"),
            models.Index(fields=["to_status", "changed_at"], name="ix_hist_status_time"),
        ]

    def __str__(self) -> str:
        return f"{self.request_id}: {self.from_status} → {self.to_status}"

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from django.conf import settings
from rest_framework import serializers

from cargo_queue import errors
from cargo_queue.awb import normalize_awb
from cargo_queue.models import (
    CargoCategory,
    QueueRequest,
    RequestStatusHistory,
    Shift,
    Ticket,
)
from cargo_queue.statuses import RequestStatus
from docks.models import Dock

_PHONE_RE = re.compile(r"^\+998\d{9}$")
_PLATE_RE = re.compile(r"^[A-Z0-9]{5,10}$")


class PermitCheckSerializer(serializers.Serializer):
    awb_number = serializers.CharField(max_length=20)


class PermitInfoSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    permit_number = serializers.CharField()
    source = serializers.CharField()  # type: ignore[assignment]
    valid_until = serializers.DateTimeField(allow_null=True)


class PermitCheckResultSerializer(serializers.Serializer):
    verified = serializers.BooleanField()
    awb_number = serializers.CharField(allow_null=True)
    reason = serializers.CharField(allow_blank=True)
    permit = PermitInfoSerializer(allow_null=True)


class ManualVerifySerializer(serializers.Serializer):
    awb_number = serializers.CharField(max_length=20)
    permit_number = serializers.CharField(max_length=100)
    valid_until = serializers.DateTimeField(required=False, allow_null=True)

    def validate_awb_number(self, value: str) -> str:
        normalized = normalize_awb(value)
        if normalized is None:
            raise serializers.ValidationError(errors.AWB_INVALID, code="awb_invalid")
        return normalized


class RegisterRequestSerializer(serializers.Serializer):
    awb_number = serializers.CharField(max_length=20)
    consignee_name = serializers.CharField(max_length=255)
    consignee_tin = serializers.CharField(max_length=20, required=False, allow_blank=True)
    representative_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    sms_phone = serializers.CharField(max_length=20)
    pieces_total = serializers.IntegerField(min_value=1, max_value=1_000_000)
    weight_kg = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))
    vehicle_plate = serializers.CharField(max_length=20, required=False, allow_blank=True)
    category = serializers.CharField(max_length=10)
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate_category(self, value: str) -> CargoCategory:
        # Custom error code, so the generic DRF-code translation does not replace the message.
        try:
            return CargoCategory.objects.get(code=value.strip().upper())
        except CargoCategory.DoesNotExist:
            raise serializers.ValidationError(
                errors.CATEGORY_UNKNOWN, code="unknown_category"
            ) from None

    def validate_awb_number(self, value: str) -> str:
        normalized = normalize_awb(value)
        if normalized is None:
            raise serializers.ValidationError(errors.AWB_INVALID, code="awb_invalid")
        return normalized

    def validate_sms_phone(self, value: str) -> str:
        cleaned = re.sub(r"[\s\-()]", "", value)
        if not _PHONE_RE.match(cleaned):
            raise serializers.ValidationError(errors.PHONE_INVALID, code="invalid_phone")
        return cleaned

    def validate_vehicle_plate(self, value: str) -> str:
        cleaned = re.sub(r"[\s\-]", "", value).upper()
        if cleaned and not _PLATE_RE.match(cleaned):
            raise serializers.ValidationError(errors.PLATE_INVALID, code="invalid_plate")
        return cleaned

    def validate_consignee_tin(self, value: str) -> str | None:
        return value.strip() or None


class HistorySerializer(serializers.ModelSerializer):
    changed_by = serializers.CharField(source="changed_by.full_name", default=None, read_only=True)

    class Meta:
        model = RequestStatusHistory
        fields = ["id", "from_status", "to_status", "changed_by", "reason", "changed_at"]
        read_only_fields = fields


class QueueRequestSerializer(serializers.ModelSerializer):
    consignee_name = serializers.CharField(source="consignee.name", read_only=True)
    category = serializers.CharField(source="category.code", read_only=True)
    shift = serializers.CharField(source="shift.name", read_only=True)
    dock = serializers.CharField(source="dock.code", default=None, allow_null=True, read_only=True)

    class Meta:
        model = QueueRequest
        fields = [
            "id",
            "queue_date",
            "queue_number",
            "awb_number",
            "consignee_name",
            "representative_name",
            "category",
            "shift",
            "dock",
            "pieces_total",
            "weight_kg",
            "vehicle_plate",
            "sms_phone",
            "status",
            "priority",
            "notes",
            "registered_at",
            "closed_at",
        ]
        read_only_fields = fields


class PaginatedQueueRequestSerializer(serializers.Serializer):
    """Shape of the paginated list response (documentation only)."""

    count = serializers.IntegerField()
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = QueueRequestSerializer(many=True)


class QueueRequestDetailSerializer(QueueRequestSerializer):
    history = HistorySerializer(many=True, read_only=True)
    permit = PermitInfoSerializer(read_only=True)

    class Meta(QueueRequestSerializer.Meta):
        fields = [*QueueRequestSerializer.Meta.fields, "permit", "history"]
        read_only_fields = fields


class TicketDataSerializer(serializers.Serializer):
    """Everything the 80 mm ticket shows (TZ 3.1 "Talonga qo‘yiladigan talablar")."""

    airport = serializers.CharField()
    queue_number = serializers.IntegerField()
    queue_date = serializers.DateField()
    awb_number = serializers.CharField()
    pieces_total = serializers.IntegerField()
    weight_kg = serializers.DecimalField(max_digits=10, decimal_places=2)
    vehicle_plate = serializers.CharField(allow_blank=True)
    registered_at = serializers.DateTimeField()
    qr_token = serializers.CharField()
    printed_at = serializers.DateTimeField()
    is_reprint = serializers.BooleanField()


def ticket_data(request: QueueRequest, ticket: Ticket) -> dict[str, Any]:
    """Ticket fields as JSON-ready values (same formats as the rest of the API)."""
    return TicketDataSerializer(
        {
            "airport": settings.AIRPORT_NAME,
            "queue_number": request.queue_number,
            "queue_date": request.queue_date,
            "awb_number": request.awb_number,
            "pieces_total": request.pieces_total,
            "weight_kg": request.weight_kg,
            "vehicle_plate": request.vehicle_plate,
            "registered_at": request.registered_at,
            "qr_token": request.qr_token,
            "printed_at": ticket.printed_at,
            "is_reprint": ticket.is_reprint,
        }
    ).data


class RegistrationResponseSerializer(QueueRequestDetailSerializer):
    ticket = TicketDataSerializer(read_only=True)

    class Meta(QueueRequestDetailSerializer.Meta):
        fields = [*QueueRequestDetailSerializer.Meta.fields, "ticket"]
        read_only_fields = fields


class TransitionSerializer(serializers.Serializer):
    to_status = serializers.ChoiceField(choices=RequestStatus.choices)
    reason = serializers.CharField(required=False, allow_blank=True)


class AssignDockSerializer(serializers.Serializer):
    dock = serializers.CharField(max_length=10)


class PrioritySerializer(serializers.Serializer):
    priority = serializers.IntegerField(min_value=0, max_value=9)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=2000)


class CategoryLookupSerializer(serializers.ModelSerializer):
    class Meta:
        model = CargoCategory
        fields = ["id", "code", "name", "special_handling", "default_priority"]
        read_only_fields = fields


class ShiftLookupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shift
        fields = ["id", "name", "starts_at", "ends_at"]
        read_only_fields = fields


class DockLookupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dock
        fields = ["id", "code", "name", "state", "is_active"]
        read_only_fields = fields


class LookupsSerializer(serializers.Serializer):
    categories = CategoryLookupSerializer(many=True)
    shifts = ShiftLookupSerializer(many=True)
    docks = DockLookupSerializer(many=True)

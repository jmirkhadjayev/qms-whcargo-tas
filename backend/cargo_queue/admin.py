from django.contrib import admin

from audit.admin_utils import ReadOnlyAdmin

from .models import (
    CargoCategory,
    Consignee,
    QueueCounter,
    QueueRequest,
    ReleasePermit,
    RequestStatusHistory,
    Shift,
    Ticket,
)


@admin.register(CargoCategory)
class CargoCategoryAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "special_handling", "default_priority"]


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ["name", "starts_at", "ends_at"]


@admin.register(Consignee)
class ConsigneeAdmin(ReadOnlyAdmin):
    list_display = ["name", "tin", "representative_name", "phone"]
    search_fields = ["name", "tin"]


@admin.register(ReleasePermit)
class ReleasePermitAdmin(ReadOnlyAdmin):
    list_display = ["awb_number", "permit_number", "source", "status", "verified_by", "valid_until"]
    list_filter = ["source", "status"]
    search_fields = ["awb_number", "permit_number"]


@admin.register(QueueRequest)
class QueueRequestAdmin(ReadOnlyAdmin):
    """View only: requests change via the registration service and the state machine."""

    list_display = ["queue_date", "queue_number", "awb_number", "status", "dock", "registered_at"]
    list_filter = ["status", "queue_date", "category"]
    search_fields = ["awb_number", "qr_token"]


@admin.register(RequestStatusHistory)
class RequestStatusHistoryAdmin(ReadOnlyAdmin):
    list_display = ["request", "from_status", "to_status", "changed_by", "changed_at"]
    list_filter = ["to_status"]


@admin.register(Ticket)
class TicketAdmin(ReadOnlyAdmin):
    list_display = ["request", "printed_at", "printed_by", "is_reprint"]


@admin.register(QueueCounter)
class QueueCounterAdmin(ReadOnlyAdmin):
    list_display = ["queue_date", "last_number"]

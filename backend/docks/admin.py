from django.contrib import admin

from audit.admin_utils import ReadOnlyAdmin

from .models import CallEvent, DisplayScreen, Dock, DockCategory, ReleaseOperation


class DockCategoryInline(admin.TabularInline):
    model = DockCategory
    extra = 0


@admin.register(Dock)
class DockAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "state", "is_active"]
    inlines = [DockCategoryInline]


@admin.register(DisplayScreen)
class DisplayScreenAdmin(admin.ModelAdmin):
    list_display = ["kind", "dock", "protocol", "address", "last_seen_at"]
    readonly_fields = ["token", "last_seen_at"]  # the token goes into the kiosk URL (?token=)


@admin.register(CallEvent)
class CallEventAdmin(ReadOnlyAdmin):
    list_display = ["request", "dock", "attempt_no", "called_at", "outcome"]


@admin.register(ReleaseOperation)
class ReleaseOperationAdmin(ReadOnlyAdmin):
    list_display = ["request", "dock", "agent", "pieces_released", "started_at", "finished_at"]

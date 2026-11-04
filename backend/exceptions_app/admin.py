from django.contrib import admin

from audit.admin_utils import ReadOnlyAdmin

from .models import ExceptionRecord


@admin.register(ExceptionRecord)
class ExceptionRecordAdmin(ReadOnlyAdmin):
    list_display = ["request", "kind", "pieces_affected", "reported_at", "resolved_at"]
    list_filter = ["kind"]

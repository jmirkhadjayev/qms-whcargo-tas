from django.contrib import admin

from audit.admin_utils import ReadOnlyAdmin

from .models import WarehouseTask


@admin.register(WarehouseTask)
class WarehouseTaskAdmin(ReadOnlyAdmin):
    list_display = ["request", "status", "assigned_to", "storage_location", "created_at"]
    list_filter = ["status"]

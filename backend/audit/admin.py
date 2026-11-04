from django.contrib import admin

from .admin_utils import ReadOnlyAdmin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(ReadOnlyAdmin):
    list_display = ["id", "created_at", "user", "action", "entity", "entity_id", "ip_address"]
    list_filter = ["action", "entity"]
    search_fields = ["entity", "user__username"]
    date_hierarchy = "created_at"

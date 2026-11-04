from django.contrib import admin

from audit.admin_utils import ReadOnlyAdmin

from .models import CheckpointPass


@admin.register(CheckpointPass)
class CheckpointPassAdmin(ReadOnlyAdmin):
    list_display = ["request", "officer", "result", "scanned_at", "exit_confirmed_at"]
    list_filter = ["result"]

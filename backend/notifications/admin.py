from django.contrib import admin

from audit.admin_utils import ReadOnlyAdmin

from .models import SmsMessage


@admin.register(SmsMessage)
class SmsMessageAdmin(ReadOnlyAdmin):
    list_display = ["request", "phone", "template", "status", "attempts", "sent_at"]
    list_filter = ["template", "status"]

from django.db import models
from django.db.models import Q


class SmsTemplate(models.TextChoices):
    REGISTERED = "REGISTERED"
    CALLED = "CALLED"
    RECALL = "RECALL"
    STATUS = "STATUS"


class SmsStatus(models.TextChoices):
    QUEUED = "QUEUED"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"


class SmsMessage(models.Model):
    request = models.ForeignKey(
        "cargo_queue.QueueRequest", on_delete=models.PROTECT, related_name="sms_messages"
    )
    phone = models.CharField(max_length=20)
    template = models.CharField(max_length=15, choices=SmsTemplate.choices)
    body = models.TextField()
    provider_msg_id = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=10, choices=SmsStatus.choices, default=SmsStatus.QUEUED)
    attempts = models.PositiveSmallIntegerField(default=0)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sms_messages"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(status__in=SmsStatus.values), name="ck_sms_status")
        ]

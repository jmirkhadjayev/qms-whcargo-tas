"""SMS notifications (TZ 7). Texts carry the ticket number, dock and a short instruction only:
no names or other personal data (the number identifies the call)."""

from __future__ import annotations

import datetime as dt
import logging
from functools import partial

from django.db import transaction
from django.utils import timezone

from accounts.settings_store import get_setting
from cargo_queue.models import QueueRequest
from integrations.sms import get_sms_gateway

from .models import SmsMessage, SmsStatus, SmsTemplate

logger = logging.getLogger(__name__)

TEMPLATES: dict[str, str] = {
    SmsTemplate.REGISTERED: (
        "Yuk navbati: №{number} talon ro‘yxatga olindi. Chaqiruvni kuting, talonni yo‘qotmang."
    ),
    SmsTemplate.CALLED: (
        "Yuk navbati: №{number}, {dock} dokka keling. Talonni o‘zingiz bilan olib keling."
    ),
    SmsTemplate.RECALL: (
        "Takroriy chaqiruv: №{number}, {dock} dokka {minutes} daqiqa ichida keling, "
        "aks holda navbatingiz o‘tib ketadi."
    ),
    SmsTemplate.STATUS: "Yuk navbati: №{number} — {text}",
}

STATUS_REQUEUED = "siz kelmadingiz, arizangiz navbat oxiriga o‘tkazildi."
STATUS_CANCELLED = "arizangiz bekor qilindi."


def render(template: str, **values: object) -> str:
    return TEMPLATES[template].format(**values)


def _dispatch(sms_id: int) -> None:
    """Hand the message to Celery. A broker outage must not fail the request that triggered the
    SMS: the row stays QUEUED and `send_pending` (periodic job) picks it up later."""
    from notifications.tasks import send_sms

    try:
        send_sms.delay(sms_id)
    except Exception:  # noqa: BLE001 - best effort, the journal row keeps the message
        logger.exception("Could not queue SMS %s; it will be sent by the periodic job", sms_id)


def queue_sms(request: QueueRequest, template: str, **values: object) -> SmsMessage:
    """Store the message (QUEUED) and hand it to Celery once the transaction is committed."""
    body = render(template, number=request.queue_number, **values)
    message = SmsMessage.objects.create(
        request=request, phone=request.sms_phone, template=template, body=body
    )
    transaction.on_commit(partial(_dispatch, message.pk))
    return message


def send_pending(older_than_seconds: int = 60) -> int:
    """Send messages that were stored but never attempted (e.g. the broker was down)."""
    cutoff = timezone.now() - dt.timedelta(seconds=older_than_seconds)
    ids = list(
        SmsMessage.objects.filter(
            status=SmsStatus.QUEUED, attempts=0, created_at__lte=cutoff
        ).values_list("pk", flat=True)
    )
    for sms_id in ids:
        deliver_sms(sms_id)
    return len(ids)


def sms_enabled_for_recall() -> bool:
    return bool(get_setting("sms_on_recall"))


def deliver_sms(sms_id: int) -> tuple[bool, bool]:
    """One delivery attempt. Returns (delivered, should_retry).

    The journal row records every attempt: attempts, sent time, provider id, last error.
    After `sms_max_attempts` failed attempts the row is FAILED and no retry is asked for.
    """
    with transaction.atomic():
        message = SmsMessage.objects.select_for_update().filter(pk=sms_id).first()
        if message is None or message.status in (SmsStatus.SENT, SmsStatus.DELIVERED):
            return True, False
        message.attempts += 1
        result = get_sms_gateway().send(message.phone, message.body)
        if result.ok:
            message.status = SmsStatus.SENT
            message.sent_at = timezone.now()
            message.provider_msg_id = result.provider_msg_id
            message.error = ""
            message.save()
            return True, False
        message.error = result.error[:1000]
        retry = message.attempts < int(get_setting("sms_max_attempts"))
        message.status = SmsStatus.QUEUED if retry else SmsStatus.FAILED
        message.save()
        return False, retry

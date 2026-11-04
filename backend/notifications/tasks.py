from celery import shared_task

from accounts.settings_store import get_setting

from .services import deliver_sms, send_pending


@shared_task(bind=True, name="notifications.send_sms", max_retries=None)
def send_sms(self, sms_id: int) -> bool:
    """Send one SMS; retried later while the gateway keeps failing (attempt limit: settings)."""
    delivered, retry = deliver_sms(sms_id)
    if retry:
        raise self.retry(countdown=int(get_setting("sms_retry_delay_sec")))
    return delivered


@shared_task(name="notifications.send_pending_sms")
def send_pending_sms() -> int:
    """Beat job: send messages that never got an attempt (broker outage, lost task)."""
    return send_pending()

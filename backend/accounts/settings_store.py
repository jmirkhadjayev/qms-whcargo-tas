"""Access to SystemSetting with built-in defaults (domain rule 9: no magic numbers in code)."""

from typing import Any

from .models import SystemSetting

# Provisional values pending customer approval (TZ 5.1, decision K28).
DEFAULTS: dict[str, Any] = {
    "no_show_timeout_min": 10,
    "max_recalls": 2,
    "no_show_action": "REQUEUE",
    "max_requeues": 1,
    # SMS (TZ 7): delivery attempts, wait between attempts, and whether a recall is texted too.
    "sms_max_attempts": 3,
    "sms_retry_delay_sec": 30,
    "sms_on_recall": True,
}


def get_setting(key: str) -> Any:
    """Return the stored value, or the default if the row does not exist."""
    try:
        return SystemSetting.objects.values_list("value", flat=True).get(key=key)
    except SystemSetting.DoesNotExist:
        if key not in DEFAULTS:
            raise KeyError(f"Unknown system setting: {key}") from None
        return DEFAULTS[key]

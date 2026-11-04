"""SMS gateways (the operator's gateway is not chosen yet; see CLAUDE.md "Tashqi tizimlar")."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Protocol

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SmsSendResult:
    ok: bool
    provider_msg_id: str = ""
    error: str = ""


class SmsGateway(Protocol):
    def send(self, phone: str, body: str) -> SmsSendResult: ...


class ConsoleSmsGateway:
    """Development gateway: writes the message to the log instead of sending it."""

    def send(self, phone: str, body: str) -> SmsSendResult:
        logger.info("SMS to %s: %s", phone, body)
        return SmsSendResult(ok=True, provider_msg_id=f"console-{uuid.uuid4().hex[:12]}")


@dataclass
class MockSmsGateway:
    """Test gateway: remembers what it was asked to send and can be told to fail."""

    sent: list[tuple[str, str]] = field(default_factory=list)
    fail_times: int = 0  # the next N sends fail
    error: str = "gateway unavailable"

    def send(self, phone: str, body: str) -> SmsSendResult:
        if self.fail_times > 0:
            self.fail_times -= 1
            return SmsSendResult(ok=False, error=self.error)
        self.sent.append((phone, body))
        return SmsSendResult(ok=True, provider_msg_id=f"mock-{len(self.sent)}")


_mock = MockSmsGateway()


def get_mock_gateway() -> MockSmsGateway:
    """The shared mock instance (tests configure and inspect it)."""
    return _mock


def get_sms_gateway() -> SmsGateway:
    name = settings.SMS_GATEWAY
    if name == "console":
        return ConsoleSmsGateway()
    if name == "mock":
        return _mock
    raise ImproperlyConfigured(f"SMS_GATEWAY={name!r} is not implemented yet (console | mock)")

"""Release-permit providers (AWERY API is not known yet — see CLAUDE.md "Tashqi tizimlar")."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from cargo_queue import errors
from cargo_queue.models import PermitSource, PermitStatus, ReleasePermit


@dataclass(frozen=True)
class PermitCheckResult:
    verified: bool
    reason: str = ""
    permit: ReleasePermit | None = None


class PermitProvider(Protocol):
    """Looks up the release permit for a normalised AWB (NNN-NNNNNNNN)."""

    def check(self, awb_number: str) -> PermitCheckResult: ...


def _result_for_existing(permit: ReleasePermit) -> PermitCheckResult:
    if permit.status == PermitStatus.REVOKED:
        return PermitCheckResult(False, errors.PERMIT_REVOKED)
    if permit.status != PermitStatus.VERIFIED:
        return PermitCheckResult(False, errors.PERMIT_NOT_VERIFIED)
    if permit.valid_until is not None and permit.valid_until < timezone.now():
        return PermitCheckResult(False, errors.PERMIT_EXPIRED)
    return PermitCheckResult(True, permit=permit)


class MockPermitProvider:
    """Demo rule: last AWB digit even -> verified, odd -> rejected."""

    def check(self, awb_number: str) -> PermitCheckResult:
        if int(awb_number[-1]) % 2 == 1:
            return PermitCheckResult(False, errors.PERMIT_NOT_FOUND)
        now = timezone.now()
        permit, _ = ReleasePermit.objects.get_or_create(
            awb_number=awb_number,
            permit_number="MOCK-" + awb_number.replace("-", ""),
            defaults={
                "source": PermitSource.MOCK,
                "status": PermitStatus.VERIFIED,
                "verified_at": now,
                "valid_until": now + timedelta(days=30),
                "raw_payload": {"provider": "mock"},
            },
        )
        return _result_for_existing(permit)


class ManualPermitProvider:
    """An authorised employee confirms the permit by hand; history is kept (TZ 9)."""

    def check(self, awb_number: str) -> PermitCheckResult:
        permits = ReleasePermit.objects.filter(awb_number=awb_number).order_by("-id")
        if not permits:
            return PermitCheckResult(False, errors.PERMIT_MANUAL_REQUIRED)
        # Prefer a usable permit; otherwise explain why the latest one is not.
        latest_result: PermitCheckResult | None = None
        for permit in permits:
            result = _result_for_existing(permit)
            if result.verified:
                return result
            latest_result = latest_result or result
        assert latest_result is not None
        return latest_result


def get_permit_provider() -> PermitProvider:
    name = settings.PERMIT_PROVIDER
    if name == "mock":
        return MockPermitProvider()
    if name == "manual":
        return ManualPermitProvider()
    raise ImproperlyConfigured(f"PERMIT_PROVIDER={name!r} is not implemented yet (mock | manual)")

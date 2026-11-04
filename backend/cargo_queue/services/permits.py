from __future__ import annotations

import datetime as dt

from django.utils import timezone

from audit import services as audit
from audit.models import AuditAction
from cargo_queue import errors
from cargo_queue.awb import normalize_awb
from cargo_queue.models import PermitSource, PermitStatus, ReleasePermit
from config.errors import DomainError
from integrations.permits import PermitCheckResult, get_permit_provider


def log_rejection(awb_raw: str, reason: str, user: object | None, ip: str | None) -> None:
    """Record a rejected registration attempt for later analysis (TZ 3.1, decision K20)."""
    audit.log(
        AuditAction.PERMIT_REJECTED,
        "permit_check",
        user=user,
        new_value={"awb_number": awb_raw, "reason": reason},
        ip=ip,
    )


def check_permit(
    awb_raw: str, user: object | None = None, ip: str | None = None
) -> PermitCheckResult:
    """Ask the configured provider; a negative answer is written to the audit log at once."""
    awb = normalize_awb(awb_raw)
    if awb is None:
        result = PermitCheckResult(False, errors.AWB_INVALID)
    else:
        result = get_permit_provider().check(awb)
    if not result.verified:
        log_rejection(awb_raw, result.reason, user, ip)
    return result


def manual_verify(
    awb_raw: str,
    permit_number: str,
    valid_until: dt.datetime | None,
    user: object,
    ip: str | None = None,
) -> ReleasePermit:
    """An authorised employee confirms a permit by hand. The record and the audit row stay."""
    awb = normalize_awb(awb_raw)
    if awb is None:
        raise DomainError("awb_invalid", errors.AWB_INVALID, 400)
    permit, created = ReleasePermit.objects.update_or_create(
        awb_number=awb,
        permit_number=permit_number.strip(),
        defaults={
            "source": PermitSource.MANUAL,
            "status": PermitStatus.VERIFIED,
            "verified_by": user,
            "verified_at": timezone.now(),
            "valid_until": valid_until,
            "raw_payload": {"provider": "manual"},
        },
    )
    audit.log(
        AuditAction.CREATE if created else AuditAction.UPDATE,
        "release_permits",
        permit.pk,
        user=user,
        new_value={"awb_number": awb, "permit_number": permit.permit_number, "status": "VERIFIED"},
        ip=ip,
    )
    return permit

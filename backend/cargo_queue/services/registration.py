"""Registering a request: permit check -> number -> request + history + audit + first ticket."""

from __future__ import annotations

import datetime as dt
import secrets
from dataclasses import dataclass
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from audit import services as audit
from audit.models import AuditAction
from cargo_queue import errors
from cargo_queue.models import CargoCategory, Consignee, QueueRequest, Ticket
from cargo_queue.services import numbering, permits, shifts, state_machine
from config.errors import DomainError
from notifications import services as sms
from notifications.models import SmsTemplate
from warehouse import services as warehouse_services


class PermitRejected(DomainError):
    """Registration blocked because there is no verified permit (domain rule 1)."""

    def __init__(self, reason: str):
        super().__init__("permit_rejected", reason, 400)


class DuplicateActiveRequest(DomainError):
    def __init__(self) -> None:
        super().__init__("duplicate_active_request", errors.DUPLICATE_ACTIVE_REQUEST, 409)


@dataclass
class RegistrationData:
    awb_number: str
    consignee_name: str
    sms_phone: str
    pieces_total: int
    weight_kg: Decimal
    category: CargoCategory
    consignee_tin: str | None = None
    representative_name: str = ""
    vehicle_plate: str = ""
    notes: str = ""


# Messages raised by the DB trigger (migration cargo_queue/0003) -> user-facing text.
_DB_PERMIT_MESSAGES = {
    "PERMIT_MISSING": errors.PERMIT_NOT_FOUND,
    "PERMIT_NOT_VERIFIED": errors.PERMIT_NOT_VERIFIED,
    "PERMIT_EXPIRED": errors.PERMIT_EXPIRED,
    "PERMIT_AWB_MISMATCH": errors.PERMIT_AWB_MISMATCH,
}


def _translate_integrity_error(exc: IntegrityError) -> DomainError | None:
    text = str(exc)
    for marker, message in _DB_PERMIT_MESSAGES.items():
        if marker in text:
            return PermitRejected(message)
    if "uq_active_request_per_awb" in text or "uq_active_request_per_permit" in text:
        return DuplicateActiveRequest()
    return None


def _get_consignee(data: RegistrationData) -> Consignee:
    if data.consignee_tin:
        consignee, created = Consignee.objects.get_or_create(
            tin=data.consignee_tin,
            defaults={
                "name": data.consignee_name,
                "representative_name": data.representative_name,
                "phone": data.sms_phone,
            },
        )
        if not created:
            consignee.name = data.consignee_name
            consignee.representative_name = data.representative_name
            consignee.phone = data.sms_phone
            consignee.save(update_fields=["name", "representative_name", "phone"])
        return consignee
    return Consignee.objects.create(
        name=data.consignee_name,
        representative_name=data.representative_name,
        phone=data.sms_phone,
    )


def register_request(
    data: RegistrationData,
    user,
    *,
    ip: str | None = None,
    now: dt.datetime | None = None,
) -> QueueRequest:
    """Create a request. The permit is re-checked here; the DB trigger is the second guard."""
    now = now or timezone.now()

    # 1) Permit check outside any transaction, so a rejection stays in the audit log.
    result = permits.check_permit(data.awb_number, user, ip)
    if not result.verified or result.permit is None:
        raise PermitRejected(result.reason)
    permit = result.permit

    if QueueRequest.objects.active().filter(awb_number=permit.awb_number).exists():
        permits.log_rejection(data.awb_number, errors.DUPLICATE_ACTIVE_REQUEST, user, ip)
        raise DuplicateActiveRequest()

    shift = shifts.shift_for(now)
    if shift is None:
        raise DomainError("no_shift", errors.NO_SHIFT, 409)

    queue_date = timezone.localtime(now).date()
    try:
        with transaction.atomic():
            consignee = _get_consignee(data)
            request = QueueRequest.objects.create(
                queue_date=queue_date,
                queue_number=numbering.next_queue_number(queue_date),
                awb_number=permit.awb_number,
                consignee=consignee,
                permit=permit,
                category=data.category,
                shift=shift,
                pieces_total=data.pieces_total,
                weight_kg=data.weight_kg,
                vehicle_plate=data.vehicle_plate,
                sms_phone=data.sms_phone,
                representative_name=data.representative_name,
                priority=data.category.default_priority,
                sort_at=now,
                qr_token=secrets.token_urlsafe(24),
                notes=data.notes,
                created_by=user,
                registered_at=now,
            )
            state_machine.record_creation(request, user)
            Ticket.objects.create(request=request, printed_by=user, printed_at=now)
            warehouse_services.create_task_for(request)
            sms.queue_sms(request, SmsTemplate.REGISTERED)
            audit.log(
                AuditAction.CREATE,
                "queue_requests",
                request.pk,
                user=user,
                new_value={
                    "queue_date": str(queue_date),
                    "queue_number": request.queue_number,
                    "awb_number": request.awb_number,
                    "permit_id": permit.pk,
                },
                ip=ip,
            )
    except IntegrityError as exc:
        # The transaction is rolled back here, so this audit row survives (decision K20).
        domain_error = _translate_integrity_error(exc)
        if domain_error is None:
            raise
        permits.log_rejection(data.awb_number, domain_error.message, user, ip)
        raise domain_error from exc
    return request

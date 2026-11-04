"""The checkpoint (NO‘P): scan the ticket, confirm the exit or hold it (TZ 5.4)."""

from __future__ import annotations

import re
from functools import partial
from typing import Any

from django.db import transaction
from django.utils import timezone

from cargo_queue import events
from cargo_queue.awb import normalize_awb
from cargo_queue.models import QueueRequest
from cargo_queue.services import closing, state_machine
from cargo_queue.statuses import RequestStatus as S
from checkpoint import errors
from checkpoint.models import CheckpointPass, CheckpointResult
from config.errors import DomainError
from exceptions_app.models import ExceptionKind, ExceptionRecord


def normalize_plate(value: str) -> str:
    return re.sub(r"[\s\-]", "", value or "").upper()


def find_request(code: str) -> QueueRequest | None:
    """By ticket QR, AWB or queue number (the latest request with that number)."""
    code = code.strip()
    if not code:
        raise DomainError("scan_empty", errors.SCAN_EMPTY, 400)
    queryset = QueueRequest.objects.select_related("consignee", "category", "dock")
    found = queryset.filter(qr_token=code).first()
    if found is None and normalize_awb(code):
        found = queryset.filter(awb_number=normalize_awb(code)).order_by("-id").first()
    if found is None and code.isdigit():
        found = queryset.filter(queue_number=int(code)).order_by("-queue_date", "-id").first()
    return found


def summary(request: QueueRequest) -> dict[str, Any]:
    """What the officer checks against the vehicle and the cargo."""
    released = closing.released_pieces(request)
    open_records = ExceptionRecord.objects.filter(request=request, resolved_at__isnull=True)
    can_confirm = request.status == S.AWAITING_CHECKPOINT
    return {
        "id": request.pk,
        "queue_number": request.queue_number,
        "awb_number": request.awb_number,
        "consignee_name": request.consignee.name,
        "category": request.category.code,
        "special_handling": request.category.special_handling,
        "vehicle_plate": request.vehicle_plate,
        "pieces_total": request.pieces_total,
        "pieces_released": released,
        "pieces_remaining": max(0, request.pieces_total - released),
        "weight_kg": request.weight_kg,
        "status": request.status,
        "dock": request.dock.code if request.dock else None,
        "can_confirm": can_confirm,
        "blocked_reason": (
            ""
            if can_confirm
            else errors.NOT_AWAITING.get(request.status, errors.NOT_AWAITING["default"])
        ),
        "open_problems": [
            {"kind": r.kind, "description": r.description}
            for r in open_records.exclude(kind=ExceptionKind.NO_SHOW)
        ],
    }


def _locked_waiting_request(request_id: int) -> QueueRequest:
    request = (
        QueueRequest.objects.select_for_update(of=("self",))
        .select_related("consignee", "category", "dock")
        .filter(pk=request_id)
        .first()
    )
    if request is None:
        raise DomainError("request_not_found", errors.NOT_FOUND, 404)
    if request.status != S.AWAITING_CHECKPOINT:
        message = errors.NOT_AWAITING.get(request.status, errors.NOT_AWAITING["default"])
        raise DomainError("not_awaiting_checkpoint", message, 409)
    return request


def confirm_exit(request_id: int, user, plate_observed: str = "") -> CheckpointPass:
    """Everything matches: the vehicle may leave. A plate that differs from the request is a
    discrepancy and has to be recorded with `hold` instead."""
    with transaction.atomic():
        request = _locked_waiting_request(request_id)
        observed = normalize_plate(plate_observed)
        registered = normalize_plate(request.vehicle_plate)
        if observed and registered and observed != registered:
            raise DomainError("plate_mismatch", errors.PLATE_MISMATCH, 409)
        state_machine.transition(request, S.EXIT_CONFIRMED, user)
        record = CheckpointPass.objects.create(
            request=request,
            officer=user,
            plate_observed=observed,
            result=CheckpointResult.APPROVED,
            exit_confirmed_at=timezone.now(),
        )
    # Nothing left to do and nothing open: the system closes the request (CLAUDE.md).
    closing.try_close(request_id)
    return record


def hold(request_id: int, user, description: str, plate_observed: str = "") -> CheckpointPass:
    """A discrepancy: stop the exit, record it, and call the shift supervisor (TZ 5.4 items 1-3).

    The request is SUSPENDED; the supervisor's decision is recorded as the resolution of the
    exception, and only then can the exit be resumed.
    """
    if not description.strip():
        raise DomainError("description_required", errors.DESCRIPTION_REQUIRED, 400)
    with transaction.atomic():
        request = _locked_waiting_request(request_id)
        observed = normalize_plate(plate_observed)
        text = description.strip()
        if observed and observed != normalize_plate(request.vehicle_plate):
            text += f" (haqiqiy raqam: {observed})"
        ExceptionRecord.objects.create(
            request=request,
            kind=ExceptionKind.CHECKPOINT,
            description=text,
            reported_by=user,
        )
        record = CheckpointPass.objects.create(
            request=request,
            officer=user,
            plate_observed=observed,
            result=CheckpointResult.HELD,
        )
        state_machine.transition(request, S.SUSPENDED, user, text)
        # The supervisor's screen learns about it at once (the exception list refreshes).
        transaction.on_commit(partial(events.publish_request_changed, request.pk, "checkpoint"))
    return record

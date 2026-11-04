"""Handing the cargo over at the dock: full or partial release (TZ 5.2)."""

from __future__ import annotations

import decimal
from functools import partial

from django.db import transaction
from django.utils import timezone

from audit import services as audit
from audit.models import AuditAction
from cargo_queue import events
from cargo_queue.models import QueueRequest
from cargo_queue.services import closing, state_machine
from cargo_queue.statuses import RequestStatus as S
from config.errors import DomainError
from docks import calls, errors
from docks.models import ReleaseOperation
from exceptions_app import services as exception_services
from exceptions_app.models import ExceptionKind, ExceptionRecord

AT_DOCK_FOR_PROBLEMS = [S.CALLED, S.ARRIVED, S.RELEASE_STARTED]


def _own_request(request_id: int, user, *, lock: bool = False) -> QueueRequest:
    queryset = QueueRequest.objects.select_related("dock")
    if lock:
        queryset = queryset.select_for_update(of=("self",))
    request = queryset.filter(pk=request_id).first()
    if request is None:
        raise DomainError("request_not_found", "Ariza topilmadi.", 404)
    calls._require_own_dock(request, user)
    return request


def _open_operation(request: QueueRequest) -> ReleaseOperation:
    operation = (
        ReleaseOperation.objects.select_for_update()
        .filter(request=request, finished_at__isnull=True)
        .order_by("-id")
        .first()
    )
    if request.status != S.RELEASE_STARTED or operation is None:
        raise DomainError("release_not_started", errors.RELEASE_NOT_STARTED, 409)
    return operation


def _notify(request_id: int) -> None:
    transaction.on_commit(partial(events.publish_request_changed, request_id, "release"))


def start(request_id: int, user) -> ReleaseOperation:
    """ARRIVED -> RELEASE_STARTED, with a release operation that counts the pieces handed over."""
    with transaction.atomic():
        request = _own_request(request_id, user, lock=True)
        state_machine.transition(request, S.RELEASE_STARTED, user)
        assert request.dock is not None
        operation = ReleaseOperation.objects.create(request=request, dock=request.dock, agent=user)
        _notify(request.pk)
    return operation


def set_progress(request_id: int, user, pieces_released: int) -> ReleaseOperation:
    """Set how many pieces this operation has handed over so far (the dock agent counts)."""
    with transaction.atomic():
        request = _own_request(request_id, user, lock=True)
        operation = _open_operation(request)
        others = closing.released_pieces(request) - operation.pieces_released
        if others + pieces_released > request.pieces_total:
            raise DomainError("release_exceeds", errors.RELEASE_EXCEEDS, 409)
        old = operation.pieces_released
        operation.pieces_released = pieces_released
        operation.save(update_fields=["pieces_released"])
        audit.log(
            AuditAction.UPDATE,
            "release_operations",
            operation.pk,
            user=user,
            old_value={"pieces_released": old},
            new_value={"pieces_released": pieces_released},
        )
        _notify(request.pk)
    return operation


def _weight_for(request: QueueRequest, operation: ReleaseOperation, override) -> decimal.Decimal:
    if override is not None:
        return decimal.Decimal(override)
    share = decimal.Decimal(operation.pieces_released) / decimal.Decimal(request.pieces_total)
    return (request.weight_kg * share).quantize(decimal.Decimal("0.01"))


def _finish_operation(request, operation, weight_override=None) -> None:
    operation.finished_at = timezone.now()
    operation.weight_released_kg = _weight_for(request, operation, weight_override)
    operation.save(update_fields=["finished_at", "weight_released_kg"])


def finish_full(request_id: int, user, weight_kg=None) -> QueueRequest:
    """Everything has been handed over: RELEASED, then on to the checkpoint (by the system)."""
    with transaction.atomic():
        request = _own_request(request_id, user, lock=True)
        operation = _open_operation(request)
        _finish_operation(request, operation, weight_kg)
        state_machine.transition(request, S.RELEASED, user)
        state_machine.transition(request, S.AWAITING_CHECKPOINT, None)
        # The earlier "partial" record is settled by the remainder being released (K17).
        ExceptionRecord.objects.filter(
            request=request, kind=ExceptionKind.PARTIAL, resolved_at__isnull=True
        ).update(resolved_at=timezone.now(), resolution="Qolgan o‘rinlar berildi.")
        _notify(request.pk)
    return request


def finish_partial(request_id: int, user, reason: str, comment: str) -> QueueRequest:
    """Only part of the cargo can be handed over. The reason and a comment are mandatory, the
    request stays open for the rest (TZ 5.2)."""
    if reason not in errors.PARTIAL_REASONS or not comment.strip():
        raise DomainError("partial_reason_required", errors.PARTIAL_REASON_REQUIRED, 400)
    with transaction.atomic():
        request = _own_request(request_id, user, lock=True)
        operation = _open_operation(request)
        label = errors.PARTIAL_REASONS[reason]
        text = f"{label}: {comment.strip()}"
        _finish_operation(request, operation)
        state_machine.transition(request, S.PARTIALLY_RELEASED, user, text)
        remaining = request.pieces_total - closing.released_pieces(request)
        record = ExceptionRecord.objects.create(
            request=request,
            kind=ExceptionKind.PARTIAL,
            pieces_affected=remaining,
            description=text,
            reported_by=user,
        )
        audit.log(
            AuditAction.CREATE,
            "exceptions",
            record.pk,
            user=user,
            new_value={"request_id": request.pk, "kind": "PARTIAL", "remaining": remaining},
        )
        state_machine.transition(request, S.AWAITING_CHECKPOINT, None)
        _notify(request.pk)
    return request


def report_problem(request_id: int, user, kind: str, description: str, pieces: int = 0):
    """The dock agent reports damage, shortage... while serving the customer (K16)."""
    request = _own_request(request_id, user)
    if request.status not in AT_DOCK_FOR_PROBLEMS:
        raise DomainError("not_at_dock", errors.NOT_AT_DOCK, 409)
    return exception_services.report(request, kind, description, user, pieces)

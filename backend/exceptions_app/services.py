"""Exceptions: shortage, damage, discrepancy, partial release, no-show (TZ 5.2 - 5.4)."""

from __future__ import annotations

from functools import partial

from django.db import transaction
from django.utils import timezone

from audit import services as audit
from audit.models import AuditAction
from cargo_queue import events
from cargo_queue.models import QueueRequest
from cargo_queue.services import closing
from config.errors import DomainError
from exceptions_app import errors
from exceptions_app.models import ExceptionKind, ExceptionRecord

# Kinds a person may report by hand (PARTIAL, NO_SHOW and CHECKPOINT are created by the flows).
REPORTABLE_KINDS = [
    ExceptionKind.MISSING,
    ExceptionKind.DAMAGE,
    ExceptionKind.SHORTAGE,
    ExceptionKind.MISMATCH,
]
# Problems that stop the warehouse task until the supervisor decides.
WAREHOUSE_BLOCKING_KINDS = REPORTABLE_KINDS


def open_exceptions(request: QueueRequest):
    return ExceptionRecord.objects.filter(request=request, resolved_at__isnull=True)


def report(
    request: QueueRequest,
    kind: str,
    description: str,
    user,
    pieces_affected: int = 0,
) -> ExceptionRecord:
    """Record a problem. The request status is left to the SUPERVISOR (decision K16)."""
    if kind not in REPORTABLE_KINDS:
        raise DomainError("problem_kind_invalid", errors.KIND_INVALID, 400)
    if not description.strip():
        raise DomainError("problem_description_required", errors.DESCRIPTION_REQUIRED, 400)
    with transaction.atomic():
        record = ExceptionRecord.objects.create(
            request=request,
            kind=kind,
            pieces_affected=pieces_affected,
            description=description.strip(),
            reported_by=user,
        )
        audit.log(
            AuditAction.CREATE,
            "exceptions",
            record.pk,
            user=user,
            new_value={"request_id": request.pk, "kind": kind},
        )
        transaction.on_commit(partial(events.publish_request_changed, request.pk, "problem"))
    return record


def resolve(exception_id: int, resolution: str, user) -> ExceptionRecord:
    """The supervisor's documented decision. Afterwards the request may move on: a paused
    warehouse task resumes, and a request waiting at EXIT_CONFIRMED may close."""
    if not resolution.strip():
        raise DomainError("resolution_required", errors.RESOLUTION_REQUIRED, 400)
    with transaction.atomic():
        record = (
            ExceptionRecord.objects.select_for_update(of=("self",))
            .select_related("request")
            .filter(pk=exception_id)
            .first()
        )
        if record is None:
            raise DomainError("exception_not_found", errors.NOT_FOUND, 404)
        if record.resolved_at is not None:
            raise DomainError("exception_resolved", errors.ALREADY_RESOLVED, 409)
        record.resolved_by = user
        record.resolved_at = timezone.now()
        record.resolution = resolution.strip()
        record.save(update_fields=["resolved_by", "resolved_at", "resolution"])
        audit.log(
            AuditAction.UPDATE,
            "exceptions",
            record.pk,
            user=user,
            old_value={"resolved": False},
            new_value={"resolved": True, "resolution": record.resolution},
        )
        transaction.on_commit(partial(events.publish_request_changed, record.request_id, "problem"))
    after_resolved(record.request_id)
    return record


def after_resolved(request_id: int) -> None:
    from warehouse import services as warehouse_services

    warehouse_services.resume_problem_tasks(request_id)
    closing.try_close(request_id)

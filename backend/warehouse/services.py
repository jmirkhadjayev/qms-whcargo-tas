"""Warehouse task workflow (TZ 3.3). Request status changes go through the state machine."""

from __future__ import annotations

from functools import partial

from django.db import transaction
from django.utils import timezone

from audit import services as audit
from audit.models import AuditAction
from cargo_queue import events
from cargo_queue.models import QueueRequest
from cargo_queue.services import state_machine
from cargo_queue.statuses import RequestStatus as S
from config.errors import DomainError
from exceptions_app.models import ExceptionKind, ExceptionRecord
from warehouse import errors
from warehouse.models import WarehouseTask
from warehouse.models import WarehouseTaskStatus as T

# What a warehouse worker may report as a problem (the other kinds belong to other roles).
PROBLEM_KINDS = [
    ExceptionKind.MISSING,
    ExceptionKind.DAMAGE,
    ExceptionKind.SHORTAGE,
    ExceptionKind.MISMATCH,
]


def _notify(task: WarehouseTask) -> None:
    transaction.on_commit(
        partial(events.publish_task_changed, task.pk, task.request_id, task.status)
    )


def _lock(task_id: int) -> WarehouseTask:
    task = (
        WarehouseTask.objects.select_for_update(of=("self",))
        .select_related("request", "request__dock")
        .filter(pk=task_id)
        .first()
    )
    if task is None:
        raise DomainError("task_not_found", errors.TASK_NOT_FOUND, 404)
    return task


def _not_suspended(task: WarehouseTask) -> None:
    if task.request.status == S.SUSPENDED:
        raise DomainError("request_suspended", errors.REQUEST_SUSPENDED, 409)


def _require(task: WarehouseTask, *allowed: str) -> None:
    if task.status not in allowed:
        raise DomainError("task_wrong_state", errors.TASK_WRONG_STATE, 409)


def notify_created(task_id: int, request_id: int) -> None:
    events.publish_task_changed(task_id, request_id, T.NEW)


def create_task_for(request: QueueRequest) -> WarehouseTask:
    """Task for the warehouse; the request moves REGISTERED -> AWAITING_PREP (by the system)."""
    with transaction.atomic():
        task = WarehouseTask.objects.create(request=request)
        state_machine.transition(request, S.AWAITING_PREP, None)
        _notify(task)
    return task


def start_task(task_id: int, user, storage_location: str | None = None) -> WarehouseTask:
    with transaction.atomic():
        task = _lock(task_id)
        _require(task, T.NEW)
        _not_suspended(task)
        state_machine.transition(task.request, S.PREP_STARTED, user)
        task.status = T.IN_PROGRESS
        task.assigned_to = user
        task.started_at = timezone.now()
        if storage_location is not None and storage_location.strip():
            task.storage_location = storage_location.strip()
        task.save()
        _notify(task)
    return task


def mark_ready(task_id: int, user) -> WarehouseTask:
    with transaction.atomic():
        task = _lock(task_id)
        _require(task, T.IN_PROGRESS)
        _not_suspended(task)
        state_machine.transition(task.request, S.CARGO_READY, user)
        # Cargo is ready: the request now waits for a dock (system step).
        state_machine.transition(task.request, S.AWAITING_DOCK, None)
        task.status = T.READY
        task.ready_at = timezone.now()
        task.save()
        _notify(task)
    return task


def report_problem(
    task_id: int, user, kind: str, description: str, pieces_affected: int = 0
) -> WarehouseTask:
    """Record a problem; the request status is left to the SUPERVISOR (decision K16)."""
    if kind not in PROBLEM_KINDS:
        raise DomainError("problem_kind_invalid", errors.PROBLEM_KIND_INVALID, 400)
    if not description.strip():
        raise DomainError("problem_description_required", errors.PROBLEM_DESCRIPTION_REQUIRED, 400)
    with transaction.atomic():
        task = _lock(task_id)
        _require(task, T.NEW, T.IN_PROGRESS, T.READY)
        record = ExceptionRecord.objects.create(
            request=task.request,
            kind=kind,
            pieces_affected=pieces_affected,
            description=description.strip(),
            reported_by=user,
        )
        task.status = T.PROBLEM
        task.save()
        audit.log(
            AuditAction.CREATE,
            "exceptions",
            record.pk,
            user=user,
            new_value={"request_id": task.request_id, "kind": kind, "source": "warehouse"},
        )
        _notify(task)
        transaction.on_commit(partial(events.publish_request_changed, task.request_id, "problem"))
    return task


def resume_problem_tasks(request_id: int) -> int:
    """After the supervisor resolved the problems of a request, its paused tasks continue
    from where they were (decision, 4-bosqich)."""
    from exceptions_app.models import ExceptionRecord
    from exceptions_app.services import WAREHOUSE_BLOCKING_KINDS

    still_open = ExceptionRecord.objects.filter(
        request_id=request_id, kind__in=WAREHOUSE_BLOCKING_KINDS, resolved_at__isnull=True
    ).exists()
    if still_open:
        return 0
    resumed = 0
    with transaction.atomic():
        tasks = WarehouseTask.objects.select_for_update().filter(
            request_id=request_id, status=T.PROBLEM
        )
        for task in tasks:
            if task.ready_at:
                task.status = T.READY
            elif task.started_at:
                task.status = T.IN_PROGRESS
            else:
                task.status = T.NEW
            task.save(update_fields=["status"])
            _notify(task)
            resumed += 1
    return resumed


def hand_over(task_id: int, user) -> WarehouseTask:
    """Confirm that the cargo was handed to the dock (TZ 3.3)."""
    with transaction.atomic():
        task = _lock(task_id)
        _require(task, T.READY)
        if task.request.dock_id is None:
            raise DomainError("dock_not_assigned", errors.DOCK_NOT_ASSIGNED, 409)
        task.status = T.HANDED_OVER
        task.handed_over_at = timezone.now()
        task.save()
        _notify(task)
    return task

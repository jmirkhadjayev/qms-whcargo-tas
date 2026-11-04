"""Calling customers to docks, the no-show timer, and dock staff readiness (TZ 3.3, 3.4, 5.1)."""

from __future__ import annotations

import datetime as dt
import logging
from collections import Counter
from functools import partial

from django.db import transaction
from django.utils import timezone

from accounts.settings_store import get_setting
from audit import services as audit
from audit.models import AuditAction
from cargo_queue import events
from cargo_queue.models import QueueRequest, RequestStatusHistory
from cargo_queue.services import state_machine
from cargo_queue.statuses import RequestStatus as S
from config.errors import DomainError
from docks import errors
from docks.models import CallEvent, CallOutcome, Dock, DockState
from exceptions_app.models import ExceptionKind, ExceptionRecord
from notifications import services as sms
from notifications.models import SmsTemplate
from warehouse.models import WarehouseTask, WarehouseTaskStatus

logger = logging.getLogger(__name__)

CARGO_READY_TASK_STATES = (WarehouseTaskStatus.READY, WarehouseTaskStatus.HANDED_OVER)
ACTIVE_AT_DOCK = [S.CALLED, S.ARRIVED, S.RELEASE_STARTED]


# --- readiness ----------------------------------------------------------------------------------


def call_blockers(request: QueueRequest) -> list[str]:
    """Why this request cannot be called now: cargo, dock and staff must all be ready (TZ 3.3)."""
    dock = request.dock
    if dock is None:
        return ["no_dock"]
    blockers = []
    task = WarehouseTask.objects.filter(request=request).order_by("-id").first()
    if task is None or task.status not in CARGO_READY_TASK_STATES:
        blockers.append("cargo_not_ready")
    if not dock.is_active or dock.state == DockState.MAINTENANCE:
        blockers.append("dock_unavailable")
    if dock.current_agent_id is None or dock.agent_ready_at is None:
        blockers.append("agent_not_ready")
    return blockers


def blockers_message(blockers: list[str]) -> str:
    return errors.CALL_NOT_READY + " ".join(errors.CALL_BLOCKERS[b] for b in blockers)


# --- call history ------------------------------------------------------------------------------


def _cycle_events(request: QueueRequest):
    """Call events since the last time the customer was sent back to the queue."""
    events_qs = CallEvent.objects.filter(request=request)
    last_requeue = (
        RequestStatusHistory.objects.filter(
            request=request, from_status=S.CALLED, to_status=S.AWAITING_DOCK
        )
        .order_by("-id")
        .first()
    )
    if last_requeue:
        events_qs = events_qs.filter(called_at__gt=last_requeue.changed_at)
    return events_qs


def recalls_used(request: QueueRequest) -> int:
    return max(0, _cycle_events(request).count() - 1)


def requeues_used(request: QueueRequest) -> int:
    return RequestStatusHistory.objects.filter(
        request=request, from_status=S.CALLED, to_status=S.AWAITING_DOCK
    ).count()


def record_call(request: QueueRequest, user, *, recall: bool) -> CallEvent:
    """A call (or recall): journal entry for the timer, plus the customer's SMS."""
    CallEvent.objects.filter(request=request, outcome=CallOutcome.PENDING).update(
        outcome=CallOutcome.NO_SHOW
    )
    attempt = CallEvent.objects.filter(request=request).count() + 1
    assert request.dock is not None
    event = CallEvent.objects.create(
        request=request,
        dock=request.dock,
        attempt_no=attempt,
        called_by=user if user is not None else None,
    )
    if not recall:
        sms.queue_sms(request, SmsTemplate.CALLED, dock=request.dock.code)
    elif sms.sms_enabled_for_recall():
        minutes = int(get_setting("no_show_timeout_min"))
        sms.queue_sms(request, SmsTemplate.RECALL, dock=request.dock.code, minutes=minutes)
    return event


def close_call(request: QueueRequest, outcome: str) -> None:
    """Settle the open call: the customer came (ARRIVED) or did not (NO_SHOW)."""
    CallEvent.objects.filter(request=request, outcome=CallOutcome.PENDING).update(
        outcome=outcome,
        arrived_at=timezone.now() if outcome == CallOutcome.ARRIVED else None,
    )
    if outcome == CallOutcome.ARRIVED:
        # A customer who finally came clears the earlier "did not show up" records.
        ExceptionRecord.objects.filter(
            request=request, kind=ExceptionKind.NO_SHOW, resolved_at__isnull=True
        ).update(resolved_at=timezone.now(), resolution="Mijoz keyin yetib keldi.")


def record_no_show(request: QueueRequest, *, cancelled: bool, as_no_show: bool = True) -> None:
    """The customer is sent back to the queue or cancelled; the SMS tells them so.

    A NO_SHOW exception is kept for the reports; it is open while the customer may still come
    (and is resolved on arrival), already resolved when the request was cancelled.
    """
    attempts = _cycle_events(request).count()
    if cancelled:
        # Nobody will come any more: earlier "did not show up" records are settled too.
        ExceptionRecord.objects.filter(
            request=request, kind=ExceptionKind.NO_SHOW, resolved_at__isnull=True
        ).update(resolved_at=timezone.now(), resolution="Ariza bekor qilindi.")
    if as_no_show:
        ExceptionRecord.objects.create(
            request=request,
            kind=ExceptionKind.NO_SHOW,
            description=f"Mijoz {attempts} marta chaqirildi, yetib kelmadi.",
            resolved_at=timezone.now() if cancelled else None,
            resolution="Ariza bekor qilindi." if cancelled else "",
        )
    sms.queue_sms(
        request,
        SmsTemplate.STATUS,
        text=sms.STATUS_CANCELLED if cancelled else sms.STATUS_REQUEUED,
    )


# --- automatic calling -------------------------------------------------------------------------


def try_call(request: QueueRequest) -> bool:
    """The system calls the customer if everything is ready; otherwise it just waits."""
    request.refresh_from_db()
    if request.status != S.DOCK_ASSIGNED or call_blockers(request):
        return False
    try:
        state_machine.transition(request, S.CALLED, None)
    except state_machine.TransitionError:
        return False  # state changed in the meantime
    return True


def call_waiting_requests() -> int:
    """Retry requests that have a dock but were not callable yet (periodic safety net)."""
    called = 0
    for request in QueueRequest.objects.filter(status=S.DOCK_ASSIGNED).select_related("dock"):
        called += try_call(request)
    return called


def process_no_shows(now: dt.datetime | None = None) -> Counter[str]:
    """The no-show timer (TZ 5.1). For each call nobody answered within the configured time:
    call again, then send the customer to the end of the queue, then cancel.
    """
    now = now or timezone.now()
    timeout = dt.timedelta(minutes=int(get_setting("no_show_timeout_min")))
    result: Counter[str] = Counter()
    due = (
        CallEvent.objects.filter(
            outcome=CallOutcome.PENDING, called_at__lte=now - timeout, request__status=S.CALLED
        )
        .values_list("request_id", flat=True)
        .distinct()
    )
    for request_id in list(due):
        result[_handle_unanswered_call(request_id, now - timeout)] += 1
    return result


def _handle_unanswered_call(request_id: int, deadline: dt.datetime) -> str:
    max_recalls = int(get_setting("max_recalls"))
    action = get_setting("no_show_action")
    max_requeues = int(get_setting("max_requeues"))
    with transaction.atomic():
        request = (
            QueueRequest.objects.select_for_update(skip_locked=True, of=("self",))
            .filter(pk=request_id, status=S.CALLED)
            .first()
        )
        if request is None:
            return "skipped"
        latest = CallEvent.objects.filter(request=request).order_by("-called_at", "-id").first()
        if latest is None or latest.outcome != CallOutcome.PENDING or latest.called_at > deadline:
            return "skipped"  # answered or called again since we looked
        if recalls_used(request) < max_recalls:
            state_machine.transition(request, S.CALLED, None)
            return "recalled"
        if action == "REQUEUE" and requeues_used(request) < max_requeues:
            state_machine.transition(request, S.AWAITING_DOCK, None)
            return "requeued"
        calls_made = _cycle_events(request).count()
        state_machine.transition(
            request,
            S.CANCELLED,
            None,
            f"Kelmaslik: mijoz {calls_made} marta chaqirilgandan so‘ng yetib kelmadi.",
        )
        return "cancelled"


# --- dock staff ---------------------------------------------------------------------------------


def agent_dock(user) -> Dock | None:
    return Dock.objects.filter(current_agent=user).first()


def _publish_dock(dock: Dock) -> None:
    transaction.on_commit(partial(events.publish_dock_changed, dock.code, dock.state))


def check_in(user, dock_code: str) -> Dock:
    """The dock agent declares readiness at a dock (K27). One agent per dock, one dock per agent."""
    with transaction.atomic():
        dock = (
            Dock.objects.select_for_update().filter(code=dock_code.upper(), is_active=True).first()
        )
        if dock is None:
            raise DomainError("dock_unknown", errors.DOCK_UNKNOWN, 404)
        if dock.state == DockState.MAINTENANCE:
            raise DomainError("dock_unavailable", errors.DOCK_NOT_AVAILABLE, 409)
        if dock.current_agent_id not in (None, user.pk):
            raise DomainError("dock_has_agent", errors.DOCK_HAS_AGENT, 409)
        for other in (
            Dock.objects.select_for_update().filter(current_agent=user).exclude(pk=dock.pk)
        ):
            _leave(other, user)
        dock.current_agent = user
        dock.agent_ready_at = timezone.now()
        dock.save(update_fields=["current_agent", "agent_ready_at"])
        audit.log(
            AuditAction.UPDATE,
            "docks",
            dock.pk,
            user=user,
            new_value={"agent_ready": True, "agent": user.pk},
        )
        _publish_dock(dock)
    # A customer may already be waiting for this dock.
    for request in QueueRequest.objects.filter(dock=dock, status=S.DOCK_ASSIGNED):
        try_call(request)
    return dock


def _leave(dock: Dock, user) -> None:
    if QueueRequest.objects.filter(dock=dock, status__in=ACTIVE_AT_DOCK).exists():
        raise DomainError("checkout_blocked", errors.CHECKOUT_BLOCKED, 409)
    dock.current_agent = None
    dock.agent_ready_at = None
    dock.save(update_fields=["current_agent", "agent_ready_at"])
    audit.log(AuditAction.UPDATE, "docks", dock.pk, user=user, new_value={"agent_ready": False})
    _publish_dock(dock)


def check_out(user) -> None:
    with transaction.atomic():
        dock = Dock.objects.select_for_update().filter(current_agent=user).first()
        if dock is not None:
            _leave(dock, user)


# --- actions on requests ------------------------------------------------------------------------


def _locked_request(request_id: int) -> QueueRequest:
    request = QueueRequest.objects.select_related("dock").filter(pk=request_id).first()
    if request is None:
        raise DomainError("request_not_found", "Ariza topilmadi.", 404)
    return request


def _require_own_dock(request: QueueRequest, user) -> None:
    """A dock agent may act only on the dock where they are signed in."""
    dock = agent_dock(user)
    if dock is None:
        raise DomainError("agent_not_at_dock", errors.AGENT_NOT_AT_DOCK, 409)
    if request.dock_id != dock.pk:
        raise DomainError("not_your_dock", errors.NOT_YOUR_DOCK, 403)


def call(request_id: int, user) -> QueueRequest:
    """Manual call by the SUPERVISOR (the system calls automatically when ready)."""
    request = _locked_request(request_id)
    state_machine.transition(request, S.CALLED, user)
    return request


def recall(request_id: int, user) -> QueueRequest:
    request = _locked_request(request_id)
    if user.role.code == "DOCK_AGENT":
        _require_own_dock(request, user)
    state_machine.transition(request, S.CALLED, user)
    return request


def arrive(request_id: int, user) -> QueueRequest:
    request = _locked_request(request_id)
    _require_own_dock(request, user)
    state_machine.transition(request, S.ARRIVED, user)
    return request

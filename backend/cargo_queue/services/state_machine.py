"""The only place where QueueRequest.status changes (domain rule 2).

The transition table below mirrors the table in CLAUDE.md. Each transition runs in one
transaction: row lock -> checks -> status change -> history row -> audit row -> WebSocket event
(sent on commit).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from functools import partial
from typing import Any

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from accounts.roles import RoleCode
from audit import services as audit
from audit.models import AuditAction
from cargo_queue import errors, events
from cargo_queue.models import QueueRequest, RequestStatusHistory
from cargo_queue.statuses import PRE_RELEASE_STATUSES, RequestStatus
from config.errors import DomainError

S = RequestStatus
R = RoleCode


class TransitionError(DomainError):
    """The requested transition is not allowed."""


@dataclass
class Context:
    request: QueueRequest
    user: object | None  # a User, or None for the system
    reason: str
    from_status: str
    to_status: str
    extra: dict[str, Any] = field(default_factory=dict)  # per-transition input (e.g. dock)


Guard = Callable[[Context], None]
Effect = Callable[[Context], list[str]]  # returns the names of the fields it changed


@dataclass(frozen=True)
class Rule:
    roles: frozenset[str] = frozenset()
    system: bool = False
    reason_required: bool = False
    guards: tuple[Guard, ...] = ()
    effects: tuple[Effect, ...] = ()


# --- guards -------------------------------------------------------------------------------


def _released_pieces(request: QueueRequest) -> int:
    from docks.models import ReleaseOperation

    total = ReleaseOperation.objects.filter(request=request).aggregate(s=Sum("pieces_released"))
    return total["s"] or 0


def g_all_released(ctx: Context) -> None:
    if _released_pieces(ctx.request) != ctx.request.pieces_total:
        raise TransitionError("release_incomplete", errors.RELEASE_INCOMPLETE, 409)


def g_partly_released(ctx: Context) -> None:
    if _released_pieces(ctx.request) >= ctx.request.pieces_total:
        raise TransitionError("release_not_partial", errors.RELEASE_NOT_PARTIAL, 409)


def g_has_remainder(ctx: Context) -> None:
    if _released_pieces(ctx.request) >= ctx.request.pieces_total:
        raise TransitionError("no_remainder", errors.NO_REMAINDER, 409)


def g_no_open_exceptions(ctx: Context) -> None:
    from exceptions_app.models import ExceptionKind, ExceptionRecord

    open_records = ExceptionRecord.objects.filter(request=ctx.request, resolved_at__isnull=True)
    if _released_pieces(ctx.request) < ctx.request.pieces_total:
        # Closing with a remainder is a documented decision (reason, SUPERVISOR); it settles the
        # "partial release" record itself, so only the other records can block it.
        open_records = open_records.exclude(kind=ExceptionKind.PARTIAL)
    if open_records.exists():
        raise TransitionError("open_exceptions", errors.OPEN_EXCEPTIONS, 409)


def g_checkpoint_cleared(ctx: Context) -> None:
    """A held exit may be resumed only after the discrepancy has been dealt with (TZ 5.4)."""
    from exceptions_app.models import ExceptionKind, ExceptionRecord

    if ExceptionRecord.objects.filter(
        request=ctx.request,
        kind__in=[ExceptionKind.CHECKPOINT, ExceptionKind.MISMATCH],
        resolved_at__isnull=True,
    ).exists():
        raise TransitionError("checkpoint_unresolved", errors.CHECKPOINT_UNRESOLVED, 409)


def g_close_with_remainder(ctx: Context) -> None:
    """A request with unreleased pieces is closed only by a SUPERVISOR with a documented reason."""
    if _released_pieces(ctx.request) < ctx.request.pieces_total and (
        ctx.user is None or not ctx.reason.strip()
    ):
        raise TransitionError("close_with_remainder", errors.CLOSE_WITH_REMAINDER, 409)


def suspended_from(request: QueueRequest) -> str | None:
    last = (
        RequestStatusHistory.objects.filter(request=request, to_status=S.SUSPENDED)
        .order_by("-id")
        .first()
    )
    return last.from_status if last else None


def g_resume_to_previous(ctx: Context) -> None:
    if suspended_from(ctx.request) != ctx.to_status:
        raise TransitionError("resume_wrong_target", errors.RESUME_WRONG_TARGET, 409)


def g_cancel_from_suspended(ctx: Context) -> None:
    if suspended_from(ctx.request) not in PRE_RELEASE_STATUSES:
        raise TransitionError("cancel_after_release", errors.CANCEL_AFTER_RELEASE, 409)


def g_dock_assignable(ctx: Context) -> None:
    """The chosen dock exists, is in service, is free and may handle this cargo category (TZ 5.3).

    The dock row is locked, so two supervisors cannot take the same dock at once.
    """
    from docks import errors as dock_errors
    from docks.models import Dock, DockCategory, DockState
    from docks.services import occupying_request

    code = ctx.extra.get("dock")
    if not code:
        raise TransitionError("dock_required", dock_errors.DOCK_REQUIRED, 400)
    dock = Dock.objects.select_for_update().filter(code=code, is_active=True).first()
    if dock is None:
        raise TransitionError("dock_unknown", dock_errors.DOCK_UNKNOWN, 404)
    if dock.state == DockState.MAINTENANCE:
        raise TransitionError("dock_maintenance", dock_errors.DOCK_MAINTENANCE, 409)
    if occupying_request(dock) is not None:
        raise TransitionError("dock_busy", dock_errors.DOCK_BUSY, 409)
    if not DockCategory.objects.filter(dock=dock, category_id=ctx.request.category_id).exists():
        raise TransitionError("dock_category_mismatch", dock_errors.DOCK_CATEGORY_MISMATCH, 409)
    ctx.extra["_dock"] = dock


def g_ready_to_call(ctx: Context) -> None:
    """Cargo ready, dock in service and dock staff ready: only then may a customer be called
    (TZ 3.3)."""
    from docks import calls

    blockers = calls.call_blockers(ctx.request)
    if blockers:
        raise TransitionError(
            "call_not_ready",
            calls.blockers_message(blockers),
            409,
            extra={"blockers": blockers},
        )


def g_recall_allowed(ctx: Context) -> None:
    """The number of repeat calls is limited by the `max_recalls` setting (TZ 5.1)."""
    from accounts.settings_store import get_setting
    from docks import calls
    from docks import errors as dock_errors

    if calls.recalls_used(ctx.request) >= int(get_setting("max_recalls")):
        raise TransitionError("recall_limit", dock_errors.RECALL_LIMIT, 409)


# Extra guards can be registered from other modules (kept for later stages).
EXTRA_GUARDS: dict[tuple[str, str], list[Guard]] = {}


def register_guard(from_status: str, to_status: str, guard: Guard) -> None:
    EXTRA_GUARDS.setdefault((from_status, to_status), []).append(guard)


# --- effects ------------------------------------------------------------------------------


def e_requeue(ctx: Context) -> list[str]:
    """Back to the end of the queue (decision K8)."""
    ctx.request.sort_at = timezone.now()
    return ["sort_at"]


def e_release_dock(ctx: Context) -> list[str]:
    ctx.request.dock = None
    return ["dock"]


def e_assign_dock(ctx: Context) -> list[str]:
    ctx.request.dock = ctx.extra["_dock"]
    return ["dock"]


def e_record_call(ctx: Context) -> list[str]:
    from docks import calls

    calls.record_call(ctx.request, ctx.user, recall=ctx.from_status == S.CALLED)
    return []


def e_call_arrived(ctx: Context) -> list[str]:
    from docks import calls
    from docks.models import CallOutcome

    calls.close_call(ctx.request, CallOutcome.ARRIVED)
    return []


def e_call_unanswered(ctx: Context) -> list[str]:
    from docks import calls
    from docks.models import CallOutcome

    calls.close_call(ctx.request, CallOutcome.NO_SHOW)
    return []


def _is_no_show_actor(ctx: Context) -> bool:
    """No-show handling is done by the system or the dock agent (not a manual SUPERVISOR cancel)."""
    return ctx.user is None or _actor_role(ctx.user) == R.DOCK_AGENT


def e_no_show_requeued(ctx: Context) -> list[str]:
    from docks import calls

    calls.record_no_show(ctx.request, cancelled=False)
    return []


def e_no_show_cancelled(ctx: Context) -> list[str]:
    from docks import calls

    calls.record_no_show(ctx.request, cancelled=True, as_no_show=_is_no_show_actor(ctx))
    return []


def e_new_warehouse_task(ctx: Context) -> list[str]:
    """The remainder goes through the warehouse again: a fresh task (decision K14)."""
    from warehouse import services as warehouse_services
    from warehouse.models import WarehouseTask

    task = WarehouseTask.objects.create(request=ctx.request)
    transaction.on_commit(partial(warehouse_services.notify_created, task.pk, ctx.request.pk))
    return []


def e_settle_partial(ctx: Context) -> list[str]:
    """Closing with a remainder is the documented decision that resolves the partial record."""
    from exceptions_app.models import ExceptionKind, ExceptionRecord

    ExceptionRecord.objects.filter(
        request=ctx.request, kind=ExceptionKind.PARTIAL, resolved_at__isnull=True
    ).update(resolved_by=ctx.user, resolved_at=timezone.now(), resolution=ctx.reason)
    return []


def e_mark_closed(ctx: Context) -> list[str]:
    ctx.request.closed_at = timezone.now()
    return ["closed_at"]


def e_reopen(ctx: Context) -> list[str]:
    ctx.request.closed_at = None
    return ["closed_at"]


# --- the transition table -----------------------------------------------------------------

TRANSITIONS: dict[tuple[str, str], Rule] = {}


def _add(
    from_statuses: Iterable[str] | str,
    to_status: str,
    *,
    roles: Iterable[str] = (),
    system: bool = False,
    reason: bool = False,
    guards: Iterable[Guard] = (),
    effects: Iterable[Effect] = (),
) -> None:
    sources = [from_statuses] if isinstance(from_statuses, str) else list(from_statuses)
    for source in sources:
        key = (str(source), str(to_status))
        old = TRANSITIONS.get(key, Rule())
        TRANSITIONS[key] = Rule(
            roles=old.roles | frozenset(str(r) for r in roles),
            system=old.system or system,
            reason_required=old.reason_required or reason,
            guards=old.guards + tuple(g for g in guards if g not in old.guards),
            effects=old.effects + tuple(e for e in effects if e not in old.effects),
        )


_add(S.REGISTERED, S.AWAITING_PREP, system=True)
_add(S.AWAITING_PREP, S.PREP_STARTED, roles=[R.WAREHOUSE])
_add(S.PREP_STARTED, S.CARGO_READY, roles=[R.WAREHOUSE])
_add(S.CARGO_READY, S.AWAITING_DOCK, system=True)
_add(
    S.AWAITING_DOCK,
    S.DOCK_ASSIGNED,
    roles=[R.SUPERVISOR],
    guards=[g_dock_assignable],
    effects=[e_assign_dock],
)
_add(
    S.DOCK_ASSIGNED,
    S.CALLED,
    roles=[R.SUPERVISOR],
    system=True,
    guards=[g_ready_to_call],
    effects=[e_record_call],
)
_add(
    S.CALLED,
    S.CALLED,
    roles=[R.DOCK_AGENT, R.SUPERVISOR],
    system=True,
    guards=[g_recall_allowed],
    effects=[e_record_call],
)  # re-call
_add(S.CALLED, S.ARRIVED, roles=[R.DOCK_AGENT], effects=[e_call_arrived])
_add(
    S.CALLED,
    S.AWAITING_DOCK,
    roles=[R.DOCK_AGENT],
    system=True,
    # no-show: back to the end of the queue
    effects=[e_call_unanswered, e_no_show_requeued, e_requeue, e_release_dock],
)
_add(
    S.CALLED,
    S.CANCELLED,
    roles=[R.DOCK_AGENT],
    system=True,
    reason=True,
    effects=[e_call_unanswered, e_no_show_cancelled],
)  # no-show regulation
_add(S.ARRIVED, S.RELEASE_STARTED, roles=[R.DOCK_AGENT])
_add(S.RELEASE_STARTED, S.RELEASED, roles=[R.DOCK_AGENT], guards=[g_all_released])
_add(
    S.RELEASE_STARTED,
    S.PARTIALLY_RELEASED,
    roles=[R.DOCK_AGENT],
    reason=True,
    guards=[g_partly_released],
)
_add([S.RELEASED, S.PARTIALLY_RELEASED], S.AWAITING_CHECKPOINT, system=True)
_add(S.AWAITING_CHECKPOINT, S.EXIT_CONFIRMED, roles=[R.CHECKPOINT])
_add(S.AWAITING_CHECKPOINT, S.SUSPENDED, roles=[R.CHECKPOINT], reason=True)
_add(
    S.EXIT_CONFIRMED,
    S.CLOSED,
    roles=[R.SUPERVISOR],
    system=True,
    guards=[g_no_open_exceptions, g_close_with_remainder],
    effects=[e_settle_partial, e_mark_closed],
)
_add(
    S.EXIT_CONFIRMED,
    S.AWAITING_PREP,
    roles=[R.SUPERVISOR],
    system=True,
    guards=[g_has_remainder],
    effects=[e_requeue, e_release_dock, e_new_warehouse_task],  # second cycle (K14)
)

_NON_FINAL = [s for s in S if s not in (S.CLOSED, S.CANCELLED, S.SUSPENDED)]
_add(_NON_FINAL, S.SUSPENDED, roles=[R.SUPERVISOR], reason=True)
_add(PRE_RELEASE_STATUSES, S.CANCELLED, roles=[R.SUPERVISOR], reason=True)
_add(S.SUSPENDED, S.CANCELLED, roles=[R.SUPERVISOR], reason=True, guards=[g_cancel_from_suspended])
for _target in _NON_FINAL:
    _add(S.SUSPENDED, _target, roles=[R.SUPERVISOR], reason=True, guards=[g_resume_to_previous])
_add(S.SUSPENDED, S.AWAITING_CHECKPOINT, guards=[g_checkpoint_cleared])
_add(S.CLOSED, S.EXIT_CONFIRMED, roles=[R.ADMIN], reason=True, effects=[e_reopen])

# Statuses whose entry is logged as a REOPEN rather than a plain TRANSITION.
_REOPEN = (S.CLOSED, S.EXIT_CONFIRMED)


# --- public API ---------------------------------------------------------------------------


def _actor_role(user: object | None) -> str | None:
    return None if user is None else user.role.code  # type: ignore[attr-defined]


def check_allowed(ctx: Context) -> Rule:
    """Validate the transition without changing anything. Raises TransitionError."""
    rule = TRANSITIONS.get((ctx.from_status, ctx.to_status))
    if rule is None:
        raise TransitionError("invalid_transition", errors.INVALID_TRANSITION, 409)

    if ctx.user is None:
        if not rule.system:
            raise TransitionError("role_forbidden", errors.ROLE_FORBIDDEN, 403)
    else:
        active = getattr(ctx.user, "is_active", False)
        if not active or _actor_role(ctx.user) not in rule.roles:
            raise TransitionError("role_forbidden", errors.ROLE_FORBIDDEN, 403)

    if rule.reason_required and not ctx.reason.strip():
        raise TransitionError("reason_required", errors.REASON_REQUIRED, 400)

    for guard in (*rule.guards, *EXTRA_GUARDS.get((ctx.from_status, ctx.to_status), [])):
        guard(ctx)
    return rule


def transition(
    request: QueueRequest,
    to_status: str,
    user: object | None,
    reason: str | None = None,
    *,
    extra: dict[str, Any] | None = None,
) -> QueueRequest:
    """Move `request` to `to_status`. `user=None` means the system."""
    with transaction.atomic():
        locked = QueueRequest.objects.select_for_update().get(pk=request.pk)
        ctx = Context(
            request=locked,
            user=user,
            reason=(reason or "").strip(),
            from_status=locked.status,
            to_status=str(to_status),
            extra=dict(extra or {}),
        )
        rule = check_allowed(ctx)
        old_dock_id = locked.dock_id

        changed = ["status"]
        for effect in rule.effects:
            changed += effect(ctx)

        locked._status_change_allowed = True
        try:
            locked.status = ctx.to_status
            locked.save(update_fields=changed)
        finally:
            locked._status_change_allowed = False

        RequestStatusHistory.objects.create(
            request=locked,
            from_status=ctx.from_status,
            to_status=ctx.to_status,
            changed_by=user if user is not None else None,  # type: ignore[misc]
            reason=ctx.reason,
        )
        is_reopen = (ctx.from_status, ctx.to_status) == _REOPEN
        audit.log(
            AuditAction.REOPEN if is_reopen else AuditAction.TRANSITION,
            "queue_requests",
            locked.pk,
            user=user,
            old_value={"status": ctx.from_status},
            new_value={"status": ctx.to_status, "reason": ctx.reason},
        )
        from docks.services import sync_dock_state

        sync_dock_state([old_dock_id, locked.dock_id])
        from docks.models import Dock

        dock_codes = list(
            Dock.objects.filter(pk__in=[d for d in (old_dock_id, locked.dock_id) if d]).values_list(
                "code", flat=True
            )
        )
        transaction.on_commit(
            partial(
                events.publish_status_changed,
                locked.pk,
                ctx.from_status,
                ctx.to_status,
                dock_codes,
            )
        )

    # Keep the caller's instance in sync.
    request.refresh_from_db()
    return request


def record_creation(request: QueueRequest, user: object | None) -> None:
    """History + event for a freshly registered request (status REGISTERED, from_status null)."""
    RequestStatusHistory.objects.create(
        request=request,
        from_status=None,
        to_status=request.status,
        changed_by=user if user is not None else None,  # type: ignore[misc]
        reason="",
    )
    transaction.on_commit(partial(events.publish_status_changed, request.pk, None, request.status))

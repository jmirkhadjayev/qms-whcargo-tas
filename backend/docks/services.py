"""Dock occupancy and state (decision K29: `docks.state` is stored and kept in sync here)."""

from __future__ import annotations

from collections.abc import Iterable
from functools import partial

from django.db import transaction

from audit import services as audit
from audit.models import AuditAction
from cargo_queue import events
from cargo_queue.models import QueueRequest
from cargo_queue.statuses import RequestStatus as S
from config.errors import DomainError
from docks import errors

from .models import Dock, DockState

# A request holds its dock from assignment until the release is finished. A suspended request
# keeps the dock too, so it can resume where it was (decision, 2-bosqich).
OCCUPYING_STATUSES = [S.DOCK_ASSIGNED, S.CALLED, S.ARRIVED, S.RELEASE_STARTED, S.SUSPENDED]


def occupying_request(dock: Dock) -> QueueRequest | None:
    return (
        QueueRequest.objects.filter(dock=dock, status__in=OCCUPYING_STATUSES)
        .select_related("category")
        .order_by("sort_at")
        .first()
    )


def sync_dock_state(dock_ids: Iterable[int | None]) -> None:
    """Recompute FREE/BUSY for the given docks. MAINTENANCE is only changed by a person."""
    for dock_id in {d for d in dock_ids if d}:
        with transaction.atomic():
            dock = Dock.objects.select_for_update().get(pk=dock_id)
            if dock.state == DockState.MAINTENANCE:
                continue
            busy = QueueRequest.objects.filter(dock=dock, status__in=OCCUPYING_STATUSES).exists()
            new_state = DockState.BUSY if busy else DockState.FREE
            if new_state != dock.state:
                dock.state = new_state
                dock.save(update_fields=["state"])
                transaction.on_commit(partial(events.publish_dock_changed, dock.code, new_state))


def set_maintenance(dock_code: str, maintenance: bool, user) -> Dock:
    """Take a dock out of service (or back). Only a free dock can go into maintenance."""
    with transaction.atomic():
        dock = Dock.objects.select_for_update().filter(code=dock_code).first()
        if dock is None:
            raise DomainError("dock_unknown", errors.DOCK_UNKNOWN, 404)
        old = dock.state
        if maintenance:
            if old == DockState.MAINTENANCE:
                return dock
            if QueueRequest.objects.filter(dock=dock, status__in=OCCUPYING_STATUSES).exists():
                raise DomainError("dock_busy", errors.DOCK_BUSY_NO_MAINTENANCE, 409)
            dock.state = DockState.MAINTENANCE
        else:
            if old != DockState.MAINTENANCE:
                return dock
            dock.state = DockState.FREE
        dock.save(update_fields=["state"])
        audit.log(
            AuditAction.UPDATE,
            "docks",
            dock.pk,
            user=user,
            old_value={"state": old},
            new_value={"state": dock.state},
        )
        transaction.on_commit(partial(events.publish_dock_changed, dock.code, dock.state))
    return dock


def free_docks_for_category(category_id: int) -> list[str]:
    """Codes of active, free docks that may handle the category (TZ 5.3)."""
    busy = set(
        QueueRequest.objects.filter(status__in=OCCUPYING_STATUSES, dock__isnull=False).values_list(
            "dock_id", flat=True
        )
    )
    return [
        dock.code
        for dock in Dock.objects.filter(
            is_active=True, state=DockState.FREE, dock_categories__category_id=category_id
        ).order_by("code")
        if dock.pk not in busy
    ]

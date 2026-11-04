"""Data for the dock agent's screen (screen 3 in CLAUDE.md)."""

from __future__ import annotations

import datetime as dt
from typing import Any

from django.utils import timezone

from accounts.settings_store import get_setting
from cargo_queue.models import QueueRequest, RequestStatusHistory
from cargo_queue.services import closing
from cargo_queue.statuses import RequestStatus as S
from docks import calls
from docks.models import (
    CallEvent,
    CallOutcome,
    Dock,
    DockCategory,
    DockState,
    ReleaseOperation,
)

CURRENT_STATUSES = [S.DOCK_ASSIGNED, S.CALLED, S.ARRIVED, S.RELEASE_STARTED]
NEXT_LIMIT = 5
HISTORY_LIMIT = 8


def _minutes_since(moment: dt.datetime) -> int:
    return max(0, int((timezone.now() - moment).total_seconds() // 60))


def _current(dock: Dock) -> dict[str, Any] | None:
    request = (
        QueueRequest.objects.filter(dock=dock, status__in=CURRENT_STATUSES)
        .select_related("consignee", "category")
        .order_by("sort_at")
        .first()
    )
    if request is None:
        return None
    event = CallEvent.objects.filter(request=request).order_by("-called_at", "-id").first()
    timeout = dt.timedelta(minutes=int(get_setting("no_show_timeout_min")))
    waiting_for_customer = (
        request.status == S.CALLED and event is not None and event.outcome == CallOutcome.PENDING
    )
    history = RequestStatusHistory.objects.filter(request=request).order_by("-id")[:HISTORY_LIMIT]
    released = closing.released_pieces(request)
    operation = ReleaseOperation.objects.filter(request=request, finished_at__isnull=True).first()
    return {
        "id": request.pk,
        "queue_number": request.queue_number,
        "awb_number": request.awb_number,
        "consignee_name": request.consignee.name,
        "representative_name": request.representative_name,
        "category": request.category.code,
        "special_handling": request.category.special_handling,
        "pieces_total": request.pieces_total,
        "weight_kg": request.weight_kg,
        "vehicle_plate": request.vehicle_plate,
        "notes": request.notes,
        "status": request.status,
        "attempt_no": event.attempt_no if event else 0,
        "recalls_left": max(0, int(get_setting("max_recalls")) - calls.recalls_used(request)),
        "timeout_at": event.called_at + timeout if waiting_for_customer and event else None,
        "blockers": calls.call_blockers(request) if request.status == S.DOCK_ASSIGNED else [],
        "pieces_released": released,
        "pieces_remaining": max(0, request.pieces_total - released),
        "operation_pieces": operation.pieces_released if operation else 0,
        "history": [
            {"from_status": h.from_status, "to_status": h.to_status, "changed_at": h.changed_at}
            for h in history
        ],
    }


def _next(dock: Dock) -> list[dict[str, Any]]:
    category_ids = DockCategory.objects.filter(dock=dock).values_list("category_id", flat=True)
    rows = (
        QueueRequest.objects.filter(status=S.AWAITING_DOCK, category_id__in=list(category_ids))
        .select_related("category")
        .order_by("-priority", "sort_at")[:NEXT_LIMIT]
    )
    return [
        {
            "queue_number": r.queue_number,
            "category": r.category.code,
            "vehicle_plate": r.vehicle_plate,
            "wait_minutes": _minutes_since(r.registered_at),
        }
        for r in rows
    ]


def me_payload(user) -> dict[str, Any]:
    dock = calls.agent_dock(user)
    if dock is None:
        free = Dock.objects.filter(
            is_active=True, current_agent__isnull=True, state__in=[DockState.FREE, DockState.BUSY]
        ).prefetch_related("dock_categories__category")
        return {
            "dock": None,
            "current": None,
            "next": [],
            "available_docks": [
                {
                    "code": d.code,
                    "name": d.name,
                    "categories": [dc.category.code for dc in d.dock_categories.all()],
                }
                for d in free
            ],
        }
    return {
        "dock": {
            "code": dock.code,
            "name": dock.name,
            "state": dock.state,
            "ready_since": dock.agent_ready_at,
        },
        "current": _current(dock),
        "next": _next(dock),
        "available_docks": [],
    }

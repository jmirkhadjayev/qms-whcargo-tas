"""Public screens (hall and dock LED): access rules and the data they may show.

These pages need no login. They are reached from allowed networks (DISPLAY_ALLOWED_IPS) or with
the screen's own token. They show only the ticket number, dock code and vehicle plate — never a
name, phone number or tax id (TZ 3.4, domain rule 7). Every payload is an explicit allow-list.
"""

from __future__ import annotations

import ipaddress
from typing import Any

from django.conf import settings
from django.utils import timezone

from cargo_queue.models import QueueRequest
from cargo_queue.statuses import RequestStatus as S
from docks import calls
from docks.models import CallEvent, DisplayScreen, Dock, ScreenKind

HALL_CALLED_LIMIT = 12
HALL_PREPARING_LIMIT = 30
PREPARING = [S.AWAITING_PREP, S.PREP_STARTED]
AT_DOCK = [S.CALLED, S.ARRIVED, S.RELEASE_STARTED]


def ip_allowed(ip: str | None) -> bool:
    if not ip:
        return False
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for entry in settings.DISPLAY_ALLOWED_IPS:
        try:
            if address in ipaddress.ip_network(entry, strict=False):
                return True
        except ValueError:
            continue
    return False


def authorize(ip: str | None, token: str | None, kind: str, dock_code: str | None = None) -> bool:
    """May this client open this screen? Allowed network, or the matching screen's token."""
    screens = DisplayScreen.objects.filter(kind=kind)
    screens = (
        screens.filter(dock__code=dock_code)
        if kind == ScreenKind.DOCK_LED
        else screens.filter(dock__isnull=True)
    )
    allowed = ip_allowed(ip)
    if not allowed and token:
        allowed = screens.filter(token=token).exists()
    if allowed:
        screens.update(last_seen_at=timezone.now())  # heartbeat for the admin
    return allowed


def _recall(request: QueueRequest) -> bool:
    return calls.recalls_used(request) > 0


def hall_payload() -> dict[str, Any]:
    called = list(
        QueueRequest.objects.filter(status=S.CALLED, dock__isnull=False)
        .select_related("dock")
        .order_by("-sort_at")
    )
    last_call = {
        e.request_id: e.called_at
        for e in CallEvent.objects.filter(request__in=called).order_by("called_at")
    }
    called.sort(key=lambda r: last_call.get(r.pk, r.sort_at), reverse=True)
    preparing = QueueRequest.objects.filter(status__in=PREPARING).order_by("sort_at")
    return {
        "called": [
            {
                "queue_number": r.queue_number,
                "dock": r.dock.code if r.dock else "",
                "vehicle_plate": r.vehicle_plate,
                "recall": _recall(r),
            }
            for r in called[:HALL_CALLED_LIMIT]
        ],
        "preparing": [{"queue_number": r.queue_number} for r in preparing[:HALL_PREPARING_LIMIT]],
    }


def led_payload(dock: Dock) -> dict[str, Any]:
    request = QueueRequest.objects.filter(dock=dock, status__in=AT_DOCK).order_by("sort_at").first()
    current = None
    if request is not None:
        current = {
            "queue_number": request.queue_number,
            "vehicle_plate": request.vehicle_plate,
            "phase": "CALLING" if request.status == S.CALLED else "SERVING",
            "recall": request.status == S.CALLED and _recall(request),
        }
    return {"dock": dock.code, "state": dock.state, "current": current}

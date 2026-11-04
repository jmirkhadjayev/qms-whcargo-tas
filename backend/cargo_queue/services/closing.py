"""Automatic closing of a request after the checkpoint (CLAUDE.md "EXIT_CONFIRMED -> CLOSED")."""

from __future__ import annotations

from django.db.models import Sum

from cargo_queue.models import QueueRequest
from cargo_queue.services import state_machine
from cargo_queue.statuses import RequestStatus as S


def released_pieces(request: QueueRequest) -> int:
    """All pieces handed over so far, over every release operation of the request."""
    from docks.models import ReleaseOperation

    total = ReleaseOperation.objects.filter(request=request).aggregate(s=Sum("pieces_released"))
    return total["s"] or 0


def remaining_pieces(request: QueueRequest) -> int:
    return max(0, request.pieces_total - released_pieces(request))


def try_close(request_id: int) -> bool:
    """Close the request if nothing is left: everything released and no unresolved exception.

    The system never closes a request with a remainder or an open exception (domain rule 6,
    TZ 11 item 11): those wait for a person's documented decision.
    """
    request = QueueRequest.objects.filter(pk=request_id).first()
    if request is None or request.status != S.EXIT_CONFIRMED:
        return False
    try:
        state_machine.transition(request, S.CLOSED, None)
    except state_machine.TransitionError:
        return False
    return True

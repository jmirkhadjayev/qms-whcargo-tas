"""WebSocket events. Always sent after commit; a broker outage must never fail a request.

Groups (CLAUDE.md / 2-bosqich): `dispatcher`, `warehouse`, `dock.<code>`.
"""

import logging
from collections.abc import Iterable
from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)

DISPATCHER_GROUP = "dispatcher"
WAREHOUSE_GROUP = "warehouse"
HALL_GROUP = "display.hall"
CHECKPOINT_GROUP = "checkpoint"


def dock_group(code: str) -> str:
    return f"dock.{code}"


def led_group(code: str) -> str:
    return f"display.led.{code}"


def _send(groups: list[str], payload: dict[str, Any]) -> None:
    layer = get_channel_layer()
    if layer is None:
        return
    for group in groups:
        try:
            async_to_sync(layer.group_send)(group, payload)
        except Exception:  # noqa: BLE001 - delivery is best effort
            logger.exception("Could not publish %s to %s", payload.get("type"), group)


def publish_status_changed(
    request_id: int,
    from_status: str | None,
    to_status: str,
    dock_codes: Iterable[str] = (),
) -> None:
    """Status changes go to the staff screens, the docks involved (the old one too, when the
    request leaves it) and the public screens (which only learn *that* something changed)."""
    groups = [DISPATCHER_GROUP, WAREHOUSE_GROUP, HALL_GROUP, CHECKPOINT_GROUP]
    for code in dict.fromkeys(dock_codes):
        groups += [dock_group(code), led_group(code)]
    _send(
        groups,
        {
            "type": "request.status",
            "request_id": request_id,
            "from_status": from_status,
            "to_status": to_status,
        },
    )


def publish_request_changed(request_id: int, what: str) -> None:
    """A request field other than status changed (priority, ...)."""
    _send(
        [DISPATCHER_GROUP, WAREHOUSE_GROUP, CHECKPOINT_GROUP],
        {"type": "request.changed", "request_id": request_id, "what": what},
    )


def publish_task_changed(task_id: int, request_id: int, status: str) -> None:
    _send(
        [WAREHOUSE_GROUP, DISPATCHER_GROUP],
        {"type": "warehouse.task", "task_id": task_id, "request_id": request_id, "status": status},
    )


def publish_dock_changed(code: str, state: str) -> None:
    _send(
        [DISPATCHER_GROUP, dock_group(code), led_group(code)],
        {"type": "dock.state", "dock": code, "state": state},
    )

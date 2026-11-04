"""WebSocket consumers (decision K25: session auth via AuthMiddlewareStack).

Groups: `dispatcher`, `warehouse`, `dock.<code>`. The server only pushes; whatever a client
sends is ignored. Events carry ids and statuses, never personal data (domain rule 7).
"""

from __future__ import annotations

from typing import Any

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from accounts.roles import RoleCode as R
from cargo_queue import events

CLOSE_FORBIDDEN = 4403
CLOSE_NOT_FOUND = 4404


@database_sync_to_async
def _role_code(user: Any) -> str | None:
    if user is None or not getattr(user, "is_authenticated", False) or not user.is_active:
        return None
    return user.role.code


class RoleGroupConsumer(AsyncJsonWebsocketConsumer):
    """Joins one group if the logged-in user has an allowed role, then forwards its events."""

    allowed_roles: frozenset[str] = frozenset()
    group: str | None = None

    async def resolve_group(self) -> str | None:
        raise NotImplementedError

    async def connect(self) -> None:
        role = await _role_code(self.scope.get("user"))
        if role not in self.allowed_roles:
            await self.close(code=CLOSE_FORBIDDEN)
            return
        group = await self.resolve_group()
        if group is None:
            await self.close(code=CLOSE_NOT_FOUND)
            return
        self.group = group
        await self.channel_layer.group_add(group, self.channel_name)
        await self.accept()

    async def disconnect(self, code: int) -> None:
        if self.group:
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive_json(self, content: Any, **kwargs: Any) -> None:
        return None  # push-only channel

    async def _forward(self, event: dict[str, Any]) -> None:
        payload = {k: v for k, v in event.items() if k != "type"}
        await self.send_json({"event": event["type"], **payload})

    # Handler names follow the event types sent from cargo_queue.events.
    async def request_status(self, event: dict[str, Any]) -> None:
        await self._forward(event)

    async def request_changed(self, event: dict[str, Any]) -> None:
        await self._forward(event)

    async def warehouse_task(self, event: dict[str, Any]) -> None:
        await self._forward(event)

    async def dock_state(self, event: dict[str, Any]) -> None:
        await self._forward(event)


class DispatcherConsumer(RoleGroupConsumer):
    allowed_roles = frozenset({R.SUPERVISOR, R.ADMIN})

    async def resolve_group(self) -> str | None:
        return events.DISPATCHER_GROUP


class WarehouseConsumer(RoleGroupConsumer):
    allowed_roles = frozenset({R.WAREHOUSE, R.SUPERVISOR})

    async def resolve_group(self) -> str | None:
        return events.WAREHOUSE_GROUP


class CheckpointConsumer(RoleGroupConsumer):
    allowed_roles = frozenset({R.CHECKPOINT, R.SUPERVISOR})

    async def resolve_group(self) -> str | None:
        return events.CHECKPOINT_GROUP


class DockConsumer(RoleGroupConsumer):
    allowed_roles = frozenset({R.DOCK_AGENT, R.SUPERVISOR})

    async def resolve_group(self) -> str | None:
        from docks.models import Dock

        code = self.scope["url_route"]["kwargs"]["code"].upper()
        exists = await database_sync_to_async(Dock.objects.filter(code=code).exists)()
        return events.dock_group(code) if exists else None


class DisplayConsumer(AsyncJsonWebsocketConsumer):
    """Public screens (no login): allowed network or the screen's token. They are only told
    *that* something changed and then fetch the data themselves, so no data travels on the socket.
    """

    kind = ""
    group: str | None = None

    def screen_target(self) -> tuple[str | None, str]:
        """(dock code or None, group name)"""
        raise NotImplementedError

    async def connect(self) -> None:
        from urllib.parse import parse_qs

        from docks import display

        query = parse_qs(self.scope.get("query_string", b"").decode())
        token = (query.get("token") or [None])[0]
        client = self.scope.get("client") or [None]
        dock_code, group = self.screen_target()
        allowed = await database_sync_to_async(display.authorize)(
            client[0], token, self.kind, dock_code
        )
        if not allowed:
            await self.close(code=CLOSE_FORBIDDEN)
            return
        if dock_code is not None:
            from docks.models import Dock

            if not await database_sync_to_async(Dock.objects.filter(code=dock_code).exists)():
                await self.close(code=CLOSE_NOT_FOUND)
                return
        self.group = group
        await self.channel_layer.group_add(group, self.channel_name)
        await self.accept()

    async def disconnect(self, code: int) -> None:
        if self.group:
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive_json(self, content: Any, **kwargs: Any) -> None:
        return None

    async def _changed(self, event: dict[str, Any]) -> None:
        await self.send_json({"event": "update"})

    request_status = _changed
    dock_state = _changed


class HallDisplayConsumer(DisplayConsumer):
    kind = "HALL"

    def screen_target(self) -> tuple[str | None, str]:
        return None, events.HALL_GROUP


class LedDisplayConsumer(DisplayConsumer):
    kind = "DOCK_LED"

    def screen_target(self) -> tuple[str | None, str]:
        code = self.scope["url_route"]["kwargs"]["code"].upper()
        return code, events.led_group(code)

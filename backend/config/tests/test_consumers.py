"""Live updates over WebSocket: who may connect, and what they receive."""

import pytest
from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser

from accounts.roles import RoleCode as R
from cargo_queue.services.state_machine import transition
from cargo_queue.statuses import RequestStatus as S
from cargo_queue.tests.factories import (
    CargoCategoryFactory,
    DockFactory,
    QueueRequestFactory,
    UserFactory,
)
from config.routing import websocket_urlpatterns
from docks.models import DockCategory
from warehouse.services import create_task_for

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.postgres]

APP = URLRouter(websocket_urlpatterns)


def user_with(role: R):
    # `role` is read in async code, so it is loaded together with the user
    from accounts.models import User

    UserFactory(role_code=role, username=f"ws_{role.value}")
    return User.objects.select_related("role").get(username=f"ws_{role.value}")


async def open_socket(path: str, user) -> tuple[WebsocketCommunicator, bool]:
    communicator = WebsocketCommunicator(APP, path)
    communicator.scope["user"] = user
    connected, _ = await communicator.connect()
    return communicator, connected


@pytest.mark.parametrize(
    ("path", "allowed"),
    [
        ("/ws/dispatcher/", {R.SUPERVISOR, R.ADMIN}),
        ("/ws/warehouse/", {R.WAREHOUSE, R.SUPERVISOR}),
        ("/ws/checkpoint/", {R.CHECKPOINT, R.SUPERVISOR}),
        ("/ws/dock/D-01/", {R.DOCK_AGENT, R.SUPERVISOR}),
    ],
)
async def test_only_the_listed_roles_may_connect(path, allowed):
    await database_sync_to_async(DockFactory)(code="D-01")
    for role in R:
        user = await database_sync_to_async(user_with)(role)
        communicator, connected = await open_socket(path, user)
        assert connected is (role in allowed), (path, role)
        await communicator.disconnect()


async def test_anonymous_visitors_are_refused():
    communicator, connected = await open_socket("/ws/dispatcher/", AnonymousUser())
    assert connected is False


async def test_unknown_dock_is_refused():
    user = await database_sync_to_async(user_with)(R.SUPERVISOR)
    communicator, connected = await open_socket("/ws/dock/D-99/", user)
    assert connected is False


async def test_deactivated_user_is_refused():
    user = await database_sync_to_async(user_with)(R.SUPERVISOR)
    user.is_active = False
    communicator, connected = await open_socket("/ws/dispatcher/", user)
    assert connected is False


def _prepare_waiting_request():
    dock = DockFactory(code="D-01")
    DockCategory.objects.create(dock=dock, category=CargoCategoryFactory(code="GEN"))
    DockFactory(code="D-02")
    return QueueRequestFactory(status=S.AWAITING_DOCK)


def _assign(request, supervisor):
    transition(request, S.DOCK_ASSIGNED, supervisor, extra={"dock": "D-01"})


async def test_status_change_reaches_dispatcher_warehouse_and_the_right_dock():
    request = await database_sync_to_async(_prepare_waiting_request)()
    boss = await database_sync_to_async(user_with)(R.SUPERVISOR)
    dispatcher, ok1 = await open_socket("/ws/dispatcher/", boss)
    warehouse, ok2 = await open_socket("/ws/warehouse/", boss)
    dock1, ok3 = await open_socket("/ws/dock/D-01/", boss)
    dock2, ok4 = await open_socket("/ws/dock/D-02/", boss)
    assert ok1 and ok2 and ok3 and ok4

    await database_sync_to_async(_assign)(request, boss)

    async def received(communicator, count):
        return {
            m["event"]: m
            for m in [await communicator.receive_json_from(timeout=3) for _ in range(count)]
        }

    # status change + the dock becoming busy: dispatcher and the chosen dock get both,
    # the warehouse only hears about the request
    for communicator in (dispatcher, dock1):
        got = await received(communicator, 2)
        assert (got["request.status"]["request_id"], got["request.status"]["to_status"]) == (
            request.pk,
            "DOCK_ASSIGNED",
        )
        assert (got["dock.state"]["dock"], got["dock.state"]["state"]) == ("D-01", "BUSY")
    got = await received(warehouse, 1)
    assert got["request.status"]["to_status"] == "DOCK_ASSIGNED"
    assert await warehouse.receive_nothing(timeout=0.3)
    assert await dock2.receive_nothing(timeout=0.3)

    for communicator in (dispatcher, warehouse, dock1, dock2):
        await communicator.disconnect()


async def test_events_carry_no_personal_data():
    request = await database_sync_to_async(_prepare_waiting_request)()
    boss = await database_sync_to_async(user_with)(R.SUPERVISOR)
    dispatcher, _ = await open_socket("/ws/dispatcher/", boss)
    await database_sync_to_async(_assign)(request, boss)
    allowed = {"event", "request_id", "from_status", "to_status", "dock", "state"}
    for _ in range(2):
        message = await dispatcher.receive_json_from(timeout=3)
        assert set(message) <= allowed
    await dispatcher.disconnect()


async def test_new_warehouse_task_is_announced():
    boss = await database_sync_to_async(user_with)(R.SUPERVISOR)
    warehouse, _ = await open_socket("/ws/warehouse/", boss)
    request = await database_sync_to_async(lambda: QueueRequestFactory(status=S.REGISTERED))()
    task = await database_sync_to_async(create_task_for)(request)

    events = []
    for _ in range(2):  # the task itself, and the REGISTERED -> AWAITING_PREP step
        events.append(await warehouse.receive_json_from(timeout=3))
    assert {e["event"] for e in events} == {"warehouse.task", "request.status"}
    task_event = next(e for e in events if e["event"] == "warehouse.task")
    assert (task_event["task_id"], task_event["status"]) == (task.pk, "NEW")
    await warehouse.disconnect()


async def test_client_messages_are_ignored():
    boss = await database_sync_to_async(user_with)(R.SUPERVISOR)
    dispatcher, _ = await open_socket("/ws/dispatcher/", boss)
    await dispatcher.send_json_to({"anything": "goes"})
    assert await dispatcher.receive_nothing(timeout=0.3)
    await dispatcher.disconnect()

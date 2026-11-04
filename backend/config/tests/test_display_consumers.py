"""Live updates for the public screens: access rules, and that no data travels on the socket."""

import pytest
from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator

from accounts.roles import RoleCode as R
from cargo_queue.services.state_machine import transition
from cargo_queue.statuses import RequestStatus as S
from cargo_queue.tests.factories import (
    CargoCategoryFactory,
    DockFactory,
    QueueRequestFactory,
    UserFactory,
    make_cargo_ready,
    make_dock_ready,
)
from config.routing import websocket_urlpatterns
from docks import calls
from docks.models import DisplayScreen, Dock, DockCategory, ScreenKind

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.postgres]

APP = URLRouter(websocket_urlpatterns)


async def open_screen(path: str, ip: str = "127.0.0.1"):
    communicator = WebsocketCommunicator(APP, path)
    communicator.scope["client"] = (ip, 50000)
    connected, _ = await communicator.connect()
    return communicator, connected


def _setup():
    boss = UserFactory(role_code=R.SUPERVISOR, username="ws_boss")
    first = DockFactory(code="D-01")
    second = DockFactory(code="D-02")
    category = CargoCategoryFactory(code="GEN")
    for dock in (first, second):
        DockCategory.objects.create(dock=dock, category=category)
    hall = DisplayScreen.objects.create(kind=ScreenKind.HALL)
    led1 = DisplayScreen.objects.create(kind=ScreenKind.DOCK_LED, dock=first)
    DisplayScreen.objects.create(kind=ScreenKind.DOCK_LED, dock=second)
    return boss, hall.token, led1.token


def _call_at_d01(boss):
    make_dock_ready(Dock.objects.get(code="D-01"))
    request = QueueRequestFactory(status=S.AWAITING_DOCK, queue_number=31)
    make_cargo_ready(request)
    transition(request, S.DOCK_ASSIGNED, boss, extra={"dock": "D-01"})
    calls.try_call(request)
    return request


async def test_allowed_network_connects_without_a_token():
    await database_sync_to_async(_setup)()
    hall, ok_hall = await open_screen("/ws/display/hall/")
    led, ok_led = await open_screen("/ws/display/led/D-01/")
    assert ok_hall and ok_led
    await hall.disconnect()
    await led.disconnect()


async def test_other_networks_need_the_screens_token(settings):
    settings.DISPLAY_ALLOWED_IPS = []
    _, hall_token, led_token = await database_sync_to_async(_setup)()
    far = "203.0.113.7"

    _, connected = await open_screen("/ws/display/hall/", far)
    assert connected is False
    _, connected = await open_screen("/ws/display/hall/?token=wrong", far)
    assert connected is False
    _, connected = await open_screen(f"/ws/display/hall/?token={led_token}", far)
    assert connected is False  # the LED's token is no good for the hall

    hall, connected = await open_screen(f"/ws/display/hall/?token={hall_token}", far)
    assert connected is True
    led, connected = await open_screen(f"/ws/display/led/D-01/?token={led_token}", far)
    assert connected is True
    _, connected = await open_screen(f"/ws/display/led/D-02/?token={led_token}", far)
    assert connected is False  # ...nor for another dock
    await hall.disconnect()
    await led.disconnect()


async def test_unknown_dock_is_refused():
    await database_sync_to_async(_setup)()
    _, connected = await open_screen("/ws/display/led/D-99/")
    assert connected is False


async def test_screens_are_only_told_that_something_changed():
    boss, _, _ = await database_sync_to_async(_setup)()
    hall, _ = await open_screen("/ws/display/hall/")
    led1, _ = await open_screen("/ws/display/led/D-01/")
    led2, _ = await open_screen("/ws/display/led/D-02/")

    await database_sync_to_async(_call_at_d01)(boss)

    assert await hall.receive_json_from(timeout=3) == {"event": "update"}
    assert await led1.receive_json_from(timeout=3) == {"event": "update"}
    assert await led2.receive_nothing(timeout=0.4)  # the other dock hears nothing
    for communicator in (hall, led1, led2):
        await communicator.disconnect()


async def test_the_dock_a_request_leaves_is_told_too():
    boss, _, _ = await database_sync_to_async(_setup)()
    request = await database_sync_to_async(_call_at_d01)(boss)
    led1, _ = await open_screen("/ws/display/led/D-01/")

    await database_sync_to_async(lambda: transition(request, S.AWAITING_DOCK, None))()

    assert await led1.receive_json_from(timeout=3) == {"event": "update"}
    await led1.disconnect()


async def test_client_messages_are_ignored():
    await database_sync_to_async(_setup)()
    hall, _ = await open_screen("/ws/display/hall/")
    await hall.send_json_to({"hello": "there"})
    assert await hall.receive_nothing(timeout=0.3)
    await hall.disconnect()

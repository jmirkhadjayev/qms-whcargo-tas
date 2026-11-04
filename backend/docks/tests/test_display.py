"""Public screens: who may open them, and that they never show personal data (TZ 3.4)."""

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.roles import RoleCode as R
from cargo_queue.services.state_machine import transition
from cargo_queue.statuses import RequestStatus as S
from cargo_queue.tests.factories import (
    ConsigneeFactory,
    DockFactory,
    QueueRequestFactory,
    UserFactory,
    make_dock_ready,
)
from docks import calls
from docks.models import DisplayScreen, DockState, ScreenKind
from docks.tests.conftest import age_call, assigned

pytestmark = [pytest.mark.django_db, pytest.mark.postgres]

PRIVATE = {
    "name": "Maxfiy Ismli MChJ",
    "tin": "987654321",
    "phone": "+998909998877",
    "rep": "Aliyev Vali",
    "notes": "ichki izoh",
}


@pytest.fixture
def hall_screen():
    return DisplayScreen.objects.create(kind=ScreenKind.HALL)


@pytest.fixture
def led_screen(dock):
    return DisplayScreen.objects.create(kind=ScreenKind.DOCK_LED, dock=dock)


def anonymous(ip: str = "127.0.0.1") -> APIClient:
    return APIClient(REMOTE_ADDR=ip)


_tins = iter(range(10**9, 10**10))


def private_request(**kwargs):
    # every consignee needs its own tax id (unique); the text we check for stays recognisable
    return QueueRequestFactory(
        consignee=ConsigneeFactory(
            name=PRIVATE["name"], tin=f"{PRIVATE['tin']}{next(_tins)}", phone=PRIVATE["phone"]
        ),
        representative_name=PRIVATE["rep"],
        notes=PRIVATE["notes"],
        sms_phone=PRIVATE["phone"],
        **kwargs,
    )


def keys(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from keys(value)
    elif isinstance(node, list):
        for item in node:
            yield from keys(item)


# --- access ---------------------------------------------------------------------------------------


def test_no_login_is_needed_from_an_allowed_network(dock, hall_screen, led_screen):
    assert anonymous().get("/api/display/hall/").status_code == 200
    assert anonymous().get("/api/display/led/D-01/").status_code == 200


def test_other_networks_are_refused_without_a_token(settings, dock, hall_screen, led_screen):
    settings.DISPLAY_ALLOWED_IPS = ["10.0.0.0/8"]
    for url in ("/api/display/hall/", "/api/display/led/D-01/"):
        response = anonymous("192.168.1.5").get(url)
        assert response.status_code == 403
        assert response.json()["detail"] == "Bu amal uchun ruxsatingiz yo‘q."


def test_an_allowed_network_range_works_without_a_token(settings, hall_screen):
    settings.DISPLAY_ALLOWED_IPS = ["10.0.0.0/8", "fd00::/8"]
    assert anonymous("10.20.30.40").get("/api/display/hall/").status_code == 200
    assert anonymous("fd00::1").get("/api/display/hall/").status_code == 200
    assert anonymous("11.0.0.1").get("/api/display/hall/").status_code == 403


def test_nothing_is_allowed_when_no_network_is_configured(settings, hall_screen):
    settings.DISPLAY_ALLOWED_IPS = []
    assert anonymous().get("/api/display/hall/").status_code == 403


def test_garbage_in_the_network_list_does_not_open_the_screens(settings, hall_screen):
    settings.DISPLAY_ALLOWED_IPS = ["not-an-ip", ""]
    assert anonymous().get("/api/display/hall/").status_code == 403


def test_a_screen_token_opens_its_own_screen_from_anywhere(settings, dock, hall_screen, led_screen):
    settings.DISPLAY_ALLOWED_IPS = []
    far = anonymous("203.0.113.9")
    assert far.get("/api/display/hall/", {"token": hall_screen.token}).status_code == 200
    assert far.get("/api/display/led/D-01/", {"token": led_screen.token}).status_code == 200


def test_a_token_is_good_for_one_screen_only(settings, dock, hall_screen, led_screen):
    settings.DISPLAY_ALLOWED_IPS = []
    other = DockFactory(code="D-02")
    DisplayScreen.objects.create(kind=ScreenKind.DOCK_LED, dock=other)
    far = anonymous("203.0.113.9")
    assert far.get("/api/display/led/D-02/", {"token": led_screen.token}).status_code == 403
    assert far.get("/api/display/led/D-01/", {"token": hall_screen.token}).status_code == 403
    assert far.get("/api/display/hall/", {"token": led_screen.token}).status_code == 403
    assert far.get("/api/display/hall/", {"token": "wrong"}).status_code == 403
    assert far.get("/api/display/hall/", {"token": ""}).status_code == 403


def test_every_screen_gets_its_own_unguessable_token(dock, hall_screen, led_screen):
    assert hall_screen.token != led_screen.token and len(hall_screen.token) >= 30


def test_unknown_dock_is_404_for_an_allowed_client(dock, hall_screen):
    DisplayScreen.objects.create(kind=ScreenKind.DOCK_LED, dock=dock)
    assert anonymous().get("/api/display/led/D-99/").status_code in (403, 404)


def test_opening_a_screen_records_a_heartbeat(dock, hall_screen):
    assert hall_screen.last_seen_at is None
    anonymous().get("/api/display/hall/")
    hall_screen.refresh_from_db()
    assert hall_screen.last_seen_at is not None
    assert (timezone.now() - hall_screen.last_seen_at).total_seconds() < 60


# --- what the hall shows ---------------------------------------------------------------------------


def test_hall_lists_called_customers_and_those_in_preparation(dock, supervisor, hall_screen):
    make_dock_ready(dock)
    called = assigned(dock, supervisor, queue_number=5, vehicle_plate="01A123BC")
    calls.try_call(called)
    QueueRequestFactory(status=S.AWAITING_PREP, queue_number=6)
    QueueRequestFactory(status=S.PREP_STARTED, queue_number=7)
    QueueRequestFactory(status=S.CARGO_READY, queue_number=8)  # neither: not on the board
    QueueRequestFactory(status=S.ARRIVED, queue_number=9)

    body = anonymous().get("/api/display/hall/").json()
    assert body["called"] == [
        {"queue_number": 5, "dock": "D-01", "vehicle_plate": "01A123BC", "recall": False}
    ]
    assert [p["queue_number"] for p in body["preparing"]] == [6, 7]


def test_a_customer_who_arrived_leaves_the_calling_list(dock, supervisor, hall_screen):
    make_dock_ready(dock)
    request = assigned(dock, supervisor, queue_number=5)
    calls.try_call(request)
    transition(request, S.ARRIVED, dock.current_agent)
    assert anonymous().get("/api/display/hall/").json()["called"] == []


def test_a_repeat_call_is_marked_and_the_newest_call_comes_first(dock, supervisor, hall_screen):
    make_dock_ready(dock)
    second_dock = make_dock_ready(DockFactory(code="D-02"), "second_agent")
    from docks.models import DockCategory

    DockCategory.objects.create(dock=second_dock, category=dock.dock_categories.get().category)
    first = assigned(dock, supervisor, queue_number=1)
    calls.try_call(first)
    second = assigned(second_dock, supervisor, queue_number=2)
    calls.try_call(second)
    age_call(first, 5)
    age_call(second, 3)  # clock ticks can tie: make the order explicit
    transition(first, S.CALLED, dock.current_agent)  # call number 1 again: now the newest

    rows = anonymous().get("/api/display/hall/").json()["called"]
    assert [(r["queue_number"], r["recall"]) for r in rows] == [(1, True), (2, False)]


# --- what a dock LED shows --------------------------------------------------------------------------


def test_led_shows_nothing_while_the_dock_is_idle(dock, led_screen):
    assert anonymous().get("/api/display/led/D-01/").json() == {
        "dock": "D-01",
        "state": "FREE",
        "current": None,
    }


def test_led_shows_the_called_customer_then_the_service(dock, supervisor, led_screen):
    make_dock_ready(dock)
    request = assigned(dock, supervisor, queue_number=12, vehicle_plate="01B777CC")
    calls.try_call(request)
    body = anonymous().get("/api/display/led/D-01/").json()
    assert body["state"] == "BUSY"
    assert body["current"] == {
        "queue_number": 12,
        "vehicle_plate": "01B777CC",
        "phase": "CALLING",
        "recall": False,
    }
    transition(request, S.ARRIVED, dock.current_agent)
    assert anonymous().get("/api/display/led/D-01/").json()["current"]["phase"] == "SERVING"


def test_led_shows_a_dock_in_maintenance(dock, led_screen):
    type(dock).objects.filter(pk=dock.pk).update(state=DockState.MAINTENANCE)
    assert anonymous().get("/api/display/led/D-01/").json()["state"] == "MAINTENANCE"


def test_a_waiting_dock_assignment_is_not_announced(dock, supervisor, led_screen):
    assigned(dock, supervisor, queue_number=3)  # DOCK_ASSIGNED, nobody called yet
    assert anonymous().get("/api/display/led/D-01/").json()["current"] is None


# --- privacy (domain rule 7) ----------------------------------------------------------------------------


def test_public_screens_never_show_personal_data(dock, supervisor, hall_screen, led_screen):
    make_dock_ready(dock)
    private_request(status=S.AWAITING_PREP, queue_number=1)
    private_request(status=S.PREP_STARTED, queue_number=2)
    request = private_request(status=S.AWAITING_DOCK, queue_number=3, vehicle_plate="01C555DD")
    from cargo_queue.tests.factories import make_cargo_ready

    make_cargo_ready(request)
    transition(request, S.DOCK_ASSIGNED, supervisor, extra={"dock": "D-01"})
    calls.try_call(request)

    allowed_keys = {
        "called",
        "preparing",
        "queue_number",
        "dock",
        "vehicle_plate",
        "recall",
        "state",
        "current",
        "phase",
    }
    for url in ("/api/display/hall/", "/api/display/led/D-01/"):
        response = anonymous().get(url)
        text = response.content.decode()
        for secret in PRIVATE.values():
            assert secret not in text, (url, secret)
        assert request.awb_number not in text and request.qr_token not in text
        assert set(keys(response.json())) <= allowed_keys, url
    assert "01C555DD" in anonymous().get("/api/display/led/D-01/").content.decode()


def test_staff_endpoints_stay_behind_login(dock):
    assert anonymous().get("/api/dispatcher/overview/").status_code in (401, 403)
    assert anonymous().get("/api/requests/").status_code in (401, 403)
    client = APIClient()
    client.force_authenticate(UserFactory(role_code=R.CHECKPOINT, username="cp"))
    assert client.get("/api/dispatcher/overview/").status_code == 403

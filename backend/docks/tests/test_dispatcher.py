import datetime as dt

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.roles import RoleCode as R
from audit.models import AuditAction, AuditLog
from cargo_queue.models import QueueRequest, RequestStatusHistory
from cargo_queue.services.state_machine import transition
from cargo_queue.statuses import RequestStatus as S
from cargo_queue.tests.factories import (
    CargoCategoryFactory,
    DockFactory,
    QueueRequestFactory,
    UserFactory,
    make_cargo_ready,
    make_dock_ready,
    release,
)
from docks import errors
from docks.models import Dock, DockCategory, DockState
from exceptions_app.models import ExceptionKind, ExceptionRecord

pytestmark = [pytest.mark.django_db, pytest.mark.postgres]


def client_for(role: R) -> APIClient:
    client = APIClient()
    client.force_authenticate(UserFactory(role_code=role, username=f"d_{role.value}"))
    return client


@pytest.fixture
def boss() -> APIClient:
    return client_for(R.SUPERVISOR)


@pytest.fixture
def dock() -> Dock:
    dock = DockFactory(code="D-01")
    DockCategory.objects.create(dock=dock, category=CargoCategoryFactory(code="GEN"))
    return dock


def waiting(**kwargs) -> QueueRequest:
    return QueueRequestFactory(status=S.AWAITING_DOCK, **kwargs)


def assign(client: APIClient, request: QueueRequest, code: str = "D-01"):
    return client.post(f"/api/requests/{request.pk}/assign-dock/", {"dock": code}, format="json")


# --- assigning a dock -----------------------------------------------------------------------


def test_assign_dock_moves_the_request_and_occupies_the_dock(boss, dock):
    request = waiting()
    response = assign(boss, request)
    assert response.status_code == 200, response.json()
    body = response.json()
    assert (body["status"], body["dock"]) == (S.DOCK_ASSIGNED, "D-01")
    dock.refresh_from_db()
    assert dock.state == DockState.BUSY
    entry = RequestStatusHistory.objects.filter(request=request).latest("id")
    assert (entry.from_status, entry.to_status) == (S.AWAITING_DOCK, S.DOCK_ASSIGNED)
    assert entry.changed_by.role.code == R.SUPERVISOR
    assert AuditLog.objects.filter(action=AuditAction.TRANSITION, entity_id=request.pk).exists()


def test_dock_code_is_case_insensitive(boss, dock):
    assert assign(boss, waiting(), "d-01").status_code == 200


@pytest.mark.parametrize(
    ("setup", "status", "code"),
    [
        ("missing", 404, "dock_unknown"),
        ("inactive", 404, "dock_unknown"),
        ("maintenance", 409, "dock_maintenance"),
        ("busy", 409, "dock_busy"),
        ("wrong_category", 409, "dock_category_mismatch"),
    ],
)
def test_assign_dock_refusals(boss, dock, setup, status, code):
    request = waiting()
    target = "D-01"
    if setup == "missing":
        target = "D-55"
    elif setup == "inactive":
        Dock.objects.filter(pk=dock.pk).update(is_active=False)
    elif setup == "maintenance":
        Dock.objects.filter(pk=dock.pk).update(state=DockState.MAINTENANCE)
    elif setup == "busy":
        other = QueueRequestFactory(status=S.AWAITING_DOCK)
        assert assign(boss, other).status_code == 200
    elif setup == "wrong_category":
        request = QueueRequestFactory(
            status=S.AWAITING_DOCK, category=CargoCategoryFactory(code="DGR")
        )
    response = assign(boss, request, target)
    assert (response.status_code, response.json()["code"]) == (status, code)
    request.refresh_from_db()
    assert request.status == S.AWAITING_DOCK and request.dock is None


def test_assign_dock_requires_the_dock_field(boss, dock):
    response = boss.post(f"/api/requests/{waiting().pk}/assign-dock/", {}, format="json")
    assert response.status_code == 400 and "dock" in response.json()


def test_only_awaiting_dock_requests_get_a_dock(boss, dock):
    request = QueueRequestFactory(status=S.CARGO_READY)
    response = assign(boss, request)
    assert response.status_code == 409 and response.json()["code"] == "invalid_transition"


def test_the_generic_transition_endpoint_cannot_skip_the_dock(boss, dock):
    request = waiting()
    response = boss.post(
        f"/api/requests/{request.pk}/transition/", {"to_status": "DOCK_ASSIGNED"}, format="json"
    )
    assert response.status_code == 400 and response.json()["code"] == "dock_required"


def test_dock_follows_the_request_through_its_life(boss, dock):
    request = waiting()
    assign(boss, request)
    dock.refresh_from_db()
    assert dock.state == DockState.BUSY

    transition(request, S.SUSPENDED, UserFactory(role_code=R.SUPERVISOR, username="s1"), "Kutish")
    dock.refresh_from_db()
    assert dock.state == DockState.BUSY  # a suspended request keeps its dock

    transition(
        request, S.DOCK_ASSIGNED, UserFactory(role_code=R.SUPERVISOR, username="s1"), "Davom"
    )
    transition(request, S.CANCELLED, UserFactory(role_code=R.SUPERVISOR, username="s1"), "Bekor")
    dock.refresh_from_db()
    assert dock.state == DockState.FREE


def test_dock_is_freed_when_the_release_is_finished(boss, dock):
    request = waiting(pieces_total=4)
    make_dock_ready(dock)
    make_cargo_ready(request)
    assign(boss, request)  # everything is ready, so the system calls the customer at once
    request.refresh_from_db()
    assert request.status == S.CALLED
    agent = dock.current_agent
    transition(request, S.ARRIVED, agent)
    transition(request, S.RELEASE_STARTED, agent)
    release(request, 4, dock)
    dock.refresh_from_db()
    assert dock.state == DockState.BUSY
    transition(request, S.RELEASED, agent)
    dock.refresh_from_db()
    assert dock.state == DockState.FREE


def test_no_show_requeue_frees_the_dock(boss, dock):
    request = waiting()
    make_dock_ready(dock)
    make_cargo_ready(request)
    assign(boss, request)
    request.refresh_from_db()
    assert request.status == S.CALLED
    transition(request, S.AWAITING_DOCK, None)
    dock.refresh_from_db()
    request.refresh_from_db()
    assert dock.state == DockState.FREE and request.dock is None


# --- maintenance ------------------------------------------------------------------------------


def test_maintenance_toggle_and_audit(boss, dock):
    on = boss.post("/api/dispatcher/docks/D-01/maintenance/", {"maintenance": True}, format="json")
    assert on.status_code == 200 and on.json()["state"] == DockState.MAINTENANCE
    entry = AuditLog.objects.get(entity="docks", entity_id=dock.pk)
    assert entry.old_value == {"state": "FREE"} and entry.new_value == {"state": "MAINTENANCE"}

    off = boss.post(
        "/api/dispatcher/docks/D-01/maintenance/", {"maintenance": False}, format="json"
    )
    assert off.json()["state"] == DockState.FREE


def test_busy_dock_cannot_go_into_maintenance(boss, dock):
    assign(boss, waiting())
    response = boss.post(
        "/api/dispatcher/docks/D-01/maintenance/", {"maintenance": True}, format="json"
    )
    assert (
        response.status_code == 409 and response.json()["detail"] == errors.DOCK_BUSY_NO_MAINTENANCE
    )


def test_maintenance_is_not_overwritten_by_request_traffic(boss, dock):
    request = waiting()
    assign(boss, request)
    Dock.objects.filter(pk=dock.pk).update(state=DockState.MAINTENANCE)  # set while occupied
    transition(request, S.CANCELLED, UserFactory(role_code=R.SUPERVISOR, username="s2"), "x")
    dock.refresh_from_db()
    assert dock.state == DockState.MAINTENANCE


def test_unknown_dock_maintenance_is_404(boss):
    response = boss.post(
        "/api/dispatcher/docks/D-99/maintenance/", {"maintenance": True}, format="json"
    )
    assert response.status_code == 404 and response.json()["code"] == "dock_unknown"


# --- priority ---------------------------------------------------------------------------------


def test_priority_is_changed_and_audited(boss):
    request = waiting()
    response = boss.post(
        f"/api/requests/{request.pk}/priority/",
        {"priority": 3, "reason": "Tez buziladi"},
        format="json",
    )
    assert response.status_code == 200 and response.json()["priority"] == 3
    entry = AuditLog.objects.get(action=AuditAction.UPDATE, entity_id=request.pk)
    assert entry.old_value == {"priority": 0}
    assert entry.new_value == {"priority": 3, "reason": "Tez buziladi"}


def test_priority_does_not_change_the_status_or_skip_anything(boss):
    request = waiting()
    boss.post(f"/api/requests/{request.pk}/priority/", {"priority": 9}, format="json")
    request.refresh_from_db()
    assert request.status == S.AWAITING_DOCK and request.dock is None


@pytest.mark.parametrize("value", [-1, 10, "x"])
def test_priority_range(boss, value):
    response = boss.post(
        f"/api/requests/{waiting().pk}/priority/", {"priority": value}, format="json"
    )
    assert response.status_code == 400 and "priority" in response.json()


def test_final_requests_keep_their_priority(boss):
    request = QueueRequestFactory(status=S.CANCELLED)
    response = boss.post(f"/api/requests/{request.pk}/priority/", {"priority": 2}, format="json")
    assert response.status_code == 409 and response.json()["code"] == "priority_final"


def test_priority_of_unknown_request_is_404(boss):
    assert (
        boss.post("/api/requests/9999/priority/", {"priority": 1}, format="json").status_code == 404
    )


# --- overview and queue ------------------------------------------------------------------------


def test_overview_counts_and_dock_cards(boss, dock):
    DockFactory(code="D-02")
    QueueRequestFactory(status=S.AWAITING_PREP)
    QueueRequestFactory(status=S.PREP_STARTED)
    QueueRequestFactory(status=S.CARGO_READY)
    waiting()
    at_dock = waiting()
    assign(boss, at_dock)
    done = QueueRequestFactory(status=S.CLOSED)
    QueueRequestFactory(status=S.CANCELLED)
    ExceptionRecord.objects.create(request=done, kind=ExceptionKind.DAMAGE)
    old = QueueRequestFactory(status=S.AWAITING_PREP)
    QueueRequest.objects.filter(pk=old.pk).update(
        registered_at=timezone.now() - dt.timedelta(minutes=90)
    )

    body = boss.get("/api/dispatcher/overview/").json()
    kpi = body["kpi"]
    assert kpi["registered_today"] == 8  # the cancelled one counts as registered, none more
    assert (kpi["in_preparation"], kpi["waiting_dock"], kpi["at_dock"]) == (3, 2, 1)
    assert kpi["completed_today"] == 1 and kpi["open_exceptions"] == 1
    assert kpi["avg_wait_minutes"] >= 15  # one request has been waiting for 90 minutes

    cards = {c["code"]: c for c in body["docks"]}
    assert cards["D-01"]["state"] == "BUSY"
    assert cards["D-01"]["request"]["queue_number"] == at_dock.queue_number
    assert cards["D-01"]["categories"] == ["GEN"]
    assert cards["D-02"]["state"] == "FREE" and cards["D-02"]["request"] is None


def test_overview_has_no_personal_data(boss, dock):
    assign(boss, waiting())
    forbidden = {"consignee_name", "representative_name", "sms_phone", "phone", "tin", "awb_number"}

    def keys(node):
        if isinstance(node, dict):
            for key, value in node.items():
                yield key
                yield from keys(value)
        elif isinstance(node, list):
            for item in node:
                yield from keys(item)

    assert not forbidden & set(keys(boss.get("/api/dispatcher/overview/").json()))


def test_queue_is_ordered_by_priority_then_waiting_time(boss, dock):
    a = waiting(queue_number=1)
    waiting(queue_number=2, priority=4)
    c = waiting(queue_number=3)
    now = timezone.now()
    QueueRequest.objects.filter(pk=a.pk).update(sort_at=now - dt.timedelta(minutes=5))
    QueueRequest.objects.filter(pk=c.pk).update(sort_at=now - dt.timedelta(minutes=30))
    QueueRequestFactory(status=S.CLOSED)
    QueueRequestFactory(status=S.CANCELLED)

    rows = boss.get("/api/dispatcher/queue/").json()
    assert [r["queue_number"] for r in rows] == [2, 3, 1]
    assert rows[0]["priority"] == 4 and rows[0]["category"] == "GEN"


def test_queue_offers_only_free_compatible_docks(boss, dock):
    free = DockFactory(code="D-02")
    DockCategory.objects.create(dock=free, category=dock.dock_categories.get().category)
    DockFactory(code="D-03")  # no category: cannot take GEN cargo
    DockFactory(code="D-04", state=DockState.MAINTENANCE)
    QueueRequestFactory(status=S.PREP_STARTED, queue_number=9)
    row = waiting(queue_number=1)
    assign(boss, waiting(queue_number=2))  # takes D-01

    rows = {r["queue_number"]: r for r in boss.get("/api/dispatcher/queue/").json()}
    assert rows[1]["free_docks"] == ["D-02"]
    assert rows[9]["free_docks"] == []  # not waiting for a dock yet
    assert row.pk == rows[1]["id"]


def test_queue_shows_the_warehouse_task_state(boss):
    from warehouse.services import create_task_for

    task = create_task_for(QueueRequestFactory(status=S.REGISTERED))
    row = boss.get("/api/dispatcher/queue/").json()[0]
    assert row["task_status"] == task.status and row["wait_minutes"] >= 0


def test_admin_may_read_but_not_control(dock):
    admin = client_for(R.ADMIN)
    assert admin.get("/api/dispatcher/overview/").status_code == 200
    assert admin.get("/api/dispatcher/queue/").status_code == 200
    assert assign(admin, waiting()).status_code == 403
    assert (
        admin.post(
            "/api/dispatcher/docks/D-01/maintenance/", {"maintenance": True}, format="json"
        ).status_code
        == 403
    )

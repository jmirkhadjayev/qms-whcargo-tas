import pytest
from rest_framework.test import APIClient

from accounts.roles import RoleCode as R
from audit.models import AuditLog
from cargo_queue.models import QueueRequest, RequestStatusHistory
from cargo_queue.services.state_machine import Context, TransitionError, check_allowed, transition
from cargo_queue.statuses import RequestStatus as S
from cargo_queue.tests.factories import DockFactory, QueueRequestFactory, UserFactory
from docks.models import DockCategory
from exceptions_app.models import ExceptionKind, ExceptionRecord
from warehouse import errors
from warehouse.models import WarehouseTask
from warehouse.models import WarehouseTaskStatus as T
from warehouse.services import create_task_for

pytestmark = [pytest.mark.django_db, pytest.mark.postgres]


def client_for(role: R, username: str | None = None) -> APIClient:
    client = APIClient()
    client.force_authenticate(UserFactory(role_code=role, username=username or f"w_{role.value}"))
    return client


@pytest.fixture
def worker() -> APIClient:
    return client_for(R.WAREHOUSE)


def make_task(**request_kwargs) -> WarehouseTask:
    """A request that has just been registered, with its warehouse task (as the system does)."""
    return create_task_for(QueueRequestFactory(status=S.REGISTERED, **request_kwargs))


def url(task: WarehouseTask, action: str) -> str:
    return f"/api/warehouse/tasks/{task.pk}/{action}/"


def statuses(request: QueueRequest) -> list[str]:
    return list(
        RequestStatusHistory.objects.filter(request=request).values_list("to_status", flat=True)
    )


def test_creating_a_task_moves_the_request_to_awaiting_prep():
    task = make_task()
    task.request.refresh_from_db()
    assert task.status == T.NEW and task.request.status == S.AWAITING_PREP
    history = RequestStatusHistory.objects.get(request=task.request)
    assert (history.from_status, history.to_status, history.changed_by) == (
        S.REGISTERED,
        S.AWAITING_PREP,
        None,
    )


def test_start_assigns_the_worker_and_stores_the_location(worker):
    task = make_task()
    response = worker.post(url(task, "start"), {"storage_location": " A-12 "}, format="json")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == T.IN_PROGRESS and body["storage_location"] == "A-12"
    assert body["assigned_to"] and body["started_at"]
    assert body["request"]["status"] == S.PREP_STARTED
    entry = RequestStatusHistory.objects.filter(request=task.request).latest("id")
    assert entry.to_status == S.PREP_STARTED and entry.changed_by.role.code == R.WAREHOUSE


def test_cannot_start_twice(worker):
    task = make_task()
    assert worker.post(url(task, "start"), {}, format="json").status_code == 200
    again = worker.post(url(task, "start"), {}, format="json")
    assert again.status_code == 409 and again.json()["code"] == "task_wrong_state"
    assert again.json()["detail"] == errors.TASK_WRONG_STATE


def test_ready_requires_start_and_then_waits_for_a_dock(worker):
    task = make_task()
    early = worker.post(url(task, "ready"), format="json")
    assert early.status_code == 409 and early.json()["code"] == "task_wrong_state"

    worker.post(url(task, "start"), {}, format="json")
    done = worker.post(url(task, "ready"), format="json")
    assert done.status_code == 200 and done.json()["status"] == T.READY
    task.request.refresh_from_db()
    assert task.request.status == S.AWAITING_DOCK
    assert statuses(task.request) == [
        S.AWAITING_PREP,
        S.PREP_STARTED,
        S.CARGO_READY,
        S.AWAITING_DOCK,
    ]
    # CARGO_READY is the worker's step, AWAITING_DOCK the system's
    last_two = RequestStatusHistory.objects.filter(request=task.request).order_by("-id")[:2]
    assert [h.changed_by_id is None for h in last_two] == [True, False]


def test_a_suspended_request_cannot_be_started_and_nothing_changes(worker):
    task = make_task()
    boss = UserFactory(role_code=R.SUPERVISOR, username="boss")
    transition(task.request, S.SUSPENDED, boss, "Tekshiruv")
    response = worker.post(url(task, "start"), {}, format="json")
    assert response.status_code == 409 and response.json()["code"] == "request_suspended"
    task.refresh_from_db()
    assert task.status == T.NEW and task.assigned_to is None


def test_problem_is_recorded_without_touching_the_request_status(worker):
    task = make_task()
    worker.post(url(task, "start"), {}, format="json")
    response = worker.post(
        url(task, "problem"),
        {"kind": "DAMAGE", "description": "Quti ezilgan", "pieces_affected": 2},
        format="json",
    )
    assert response.status_code == 200 and response.json()["status"] == T.PROBLEM
    task.request.refresh_from_db()
    assert task.request.status == S.PREP_STARTED  # the SUPERVISOR decides (K16)
    record = ExceptionRecord.objects.get(request=task.request)
    assert (record.kind, record.pieces_affected, record.description) == (
        ExceptionKind.DAMAGE,
        2,
        "Quti ezilgan",
    )
    assert record.reported_by.role.code == R.WAREHOUSE and record.is_open
    assert AuditLog.objects.filter(entity="exceptions", entity_id=record.pk).exists()


def test_problem_validation(worker):
    task = make_task()
    wrong_kind = worker.post(url(task, "problem"), {"kind": "NO_SHOW", "description": "x"})
    assert wrong_kind.status_code == 400 and "kind" in wrong_kind.json()
    no_text = worker.post(url(task, "problem"), {"kind": "MISSING", "description": ""})
    assert no_text.status_code == 400 and "description" in no_text.json()
    assert not ExceptionRecord.objects.exists()


def test_a_task_with_a_problem_cannot_continue(worker):
    task = make_task()
    worker.post(url(task, "problem"), {"kind": "MISSING", "description": "Yuk topilmadi"})
    for action in ("start", "ready", "handover"):
        response = worker.post(url(task, action), {}, format="json")
        assert response.status_code == 409, action


def test_open_problem_blocks_closing_the_request(worker):
    """Domain rule 6 seen from the warehouse: the problem stays open until someone resolves it."""
    task = make_task()
    worker.post(url(task, "problem"), {"kind": "SHORTAGE", "description": "Kamomad"})
    request = task.request
    ctx = Context(request, None, "", S.EXIT_CONFIRMED, S.CLOSED)
    with pytest.raises(TransitionError) as err:
        check_allowed(ctx)
    assert err.value.code == "open_exceptions"


def test_handover_needs_a_dock(worker):
    task = make_task()
    worker.post(url(task, "start"), {}, format="json")
    worker.post(url(task, "ready"), format="json")
    early = worker.post(url(task, "handover"), format="json")
    assert early.status_code == 409 and early.json()["code"] == "dock_not_assigned"

    dock = DockFactory(code="D-31")
    DockCategory.objects.create(dock=dock, category=task.request.category)
    boss = client_for(R.SUPERVISOR)
    assert (
        boss.post(
            f"/api/requests/{task.request.pk}/assign-dock/", {"dock": "D-31"}, format="json"
        ).status_code
        == 200
    )

    done = worker.post(url(task, "handover"), format="json")
    assert done.status_code == 200 and done.json()["status"] == T.HANDED_OVER
    assert done.json()["handed_over_at"]


def test_unknown_task_is_404_in_uzbek(worker):
    response = worker.post("/api/warehouse/tasks/99999/start/", {}, format="json")
    assert response.status_code == 404 and response.json()["detail"] == errors.TASK_NOT_FOUND


# --- list and scan --------------------------------------------------------------------------


def test_list_orders_by_priority_and_hides_finished_work(worker):
    low = make_task(queue_number=1)
    high = make_task(queue_number=2, priority=5)
    handed = make_task(queue_number=3)
    WarehouseTask.objects.filter(pk=handed.pk).update(status=T.HANDED_OVER)
    cancelled = make_task(queue_number=4)
    boss = UserFactory(role_code=R.SUPERVISOR, username="boss")
    transition(cancelled.request, S.CANCELLED, boss, "Mijoz rad etdi")

    rows = worker.get("/api/warehouse/tasks/").json()
    assert [r["id"] for r in rows] == [high.pk, low.pk]
    first = rows[0]["request"]
    assert first["queue_number"] == 2 and first["category"] and "awb_number" in first
    assert "special_handling" in first and "weight_kg" in first

    assert [r["id"] for r in worker.get("/api/warehouse/tasks/?status=HANDED_OVER").json()] == [
        handed.pk
    ]
    assert [
        r["id"] for r in worker.get(f"/api/warehouse/tasks/?q={low.request.awb_number}").json()
    ] == [low.pk]


def test_scan_finds_the_task_by_ticket_token_awb_or_number(worker):
    task = make_task(queue_number=17)
    request = task.request
    for code in (request.qr_token, request.awb_number, request.awb_number.replace("-", ""), "17"):
        response = worker.get("/api/warehouse/tasks/scan/", {"code": code})
        assert response.status_code == 200, code
        assert response.json()["id"] == task.pk


def test_scan_errors(worker):
    assert worker.get("/api/warehouse/tasks/scan/", {"code": "nothing"}).status_code == 404
    empty = worker.get("/api/warehouse/tasks/scan/")
    assert empty.status_code == 400 and empty.json()["code"] == "scan_empty"


def test_supervisor_can_look_but_not_work():
    task = make_task()
    boss = client_for(R.SUPERVISOR)
    assert boss.get("/api/warehouse/tasks/").status_code == 200
    assert boss.post(url(task, "start"), {}, format="json").status_code == 403

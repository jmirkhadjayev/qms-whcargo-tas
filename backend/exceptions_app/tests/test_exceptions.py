"""Exceptions and their resolution (TZ 5.2 - 5.4, domain rule 6)."""

import pytest

from accounts.roles import RoleCode as R
from audit.models import AuditAction, AuditLog
from cargo_queue.models import QueueRequest
from cargo_queue.services.state_machine import transition
from cargo_queue.statuses import RequestStatus as S
from cargo_queue.tests.factories import QueueRequestFactory, UserFactory, release
from docks.tests.conftest import client_for
from exceptions_app import errors
from exceptions_app.models import ExceptionKind, ExceptionRecord
from warehouse.models import WarehouseTask
from warehouse.models import WarehouseTaskStatus as T
from warehouse.services import create_task_for

pytestmark = [pytest.mark.django_db, pytest.mark.postgres]


@pytest.fixture
def boss():
    return client_for(UserFactory(role_code=R.SUPERVISOR, username="boss_x"))


def record(request=None, kind=ExceptionKind.DAMAGE, **kwargs):
    request = request or QueueRequestFactory()
    return ExceptionRecord.objects.create(
        request=request, kind=kind, description="Tavsif", **kwargs
    )


# --- the list --------------------------------------------------------------------------------------


def test_the_list_shows_open_problems_and_hides_no_show_bookkeeping(boss):
    first = record(kind=ExceptionKind.DAMAGE)
    second = record(kind=ExceptionKind.CHECKPOINT)
    record(kind=ExceptionKind.NO_SHOW)
    done = record(kind=ExceptionKind.SHORTAGE)
    ExceptionRecord.objects.filter(pk=done.pk).update(resolved_at=first.reported_at)

    rows = boss.get("/api/exceptions/").json()
    assert {r["id"] for r in rows} == {first.pk, second.pk}
    row = next(r for r in rows if r["id"] == first.pk)
    assert row["queue_number"] == first.request.queue_number and row["kind"] == "DAMAGE"
    assert row["request_status"] == S.REGISTERED and row["resolved_at"] is None


def test_the_list_can_be_filtered(boss):
    damage = record(kind=ExceptionKind.DAMAGE)
    no_show = record(kind=ExceptionKind.NO_SHOW)
    done = record(kind=ExceptionKind.SHORTAGE)
    ExceptionRecord.objects.filter(pk=done.pk).update(resolved_at=damage.reported_at)

    def ids(query):
        return {r["id"] for r in boss.get(f"/api/exceptions/{query}").json()}

    assert ids("?status=resolved") == {done.pk}
    assert ids("?status=all") == {damage.pk, done.pk}
    assert ids("?kind=NO_SHOW") == {no_show.pk}
    assert ids("?status=all&kind=DAMAGE") == {damage.pk}


def test_the_admin_may_read_but_not_decide():
    admin = client_for(UserFactory(role_code=R.ADMIN, username="adm_x"))
    item = record()
    assert admin.get("/api/exceptions/").status_code == 200
    response = admin.post(f"/api/exceptions/{item.pk}/resolve/", {"resolution": "x"}, format="json")
    assert response.status_code == 403


# --- resolving -----------------------------------------------------------------------------------------


def test_the_supervisor_resolves_with_a_documented_decision(boss):
    item = record()
    response = boss.post(
        f"/api/exceptions/{item.pk}/resolve/",
        {"resolution": "Sug‘urta bilan qoplandi"},
        format="json",
    )
    assert response.status_code == 200
    body = response.json()
    assert (
        body["resolution"] == "Sug‘urta bilan qoplandi"
        and body["resolved_by"]
        and body["resolved_at"]
    )
    item.refresh_from_db()
    assert not item.is_open and item.resolved_by.role.code == R.SUPERVISOR
    entry = AuditLog.objects.get(action=AuditAction.UPDATE, entity="exceptions", entity_id=item.pk)
    assert entry.old_value == {"resolved": False} and entry.new_value["resolved"] is True


@pytest.mark.parametrize("body", [{}, {"resolution": ""}, {"resolution": "   "}])
def test_the_decision_must_be_written_down(boss, body):
    item = record()
    response = boss.post(f"/api/exceptions/{item.pk}/resolve/", body, format="json")
    assert response.status_code == 400
    assert ExceptionRecord.objects.get(pk=item.pk).is_open


def test_an_exception_is_resolved_once(boss):
    item = record()
    boss.post(f"/api/exceptions/{item.pk}/resolve/", {"resolution": "Birinchi"}, format="json")
    again = boss.post(
        f"/api/exceptions/{item.pk}/resolve/", {"resolution": "Ikkinchi"}, format="json"
    )
    assert again.status_code == 409 and again.json()["detail"] == errors.ALREADY_RESOLVED
    assert ExceptionRecord.objects.get(pk=item.pk).resolution == "Birinchi"


def test_unknown_exception_is_404_in_uzbek(boss):
    response = boss.post("/api/exceptions/9999/resolve/", {"resolution": "x"}, format="json")
    assert response.status_code == 404 and response.json()["detail"] == errors.NOT_FOUND


# --- what resolving sets in motion -------------------------------------------------------------------------


def test_resolving_the_last_problem_lets_a_closed_off_request_close(boss):
    """Domain rule 6 from the other side: once nothing is open, the request closes itself."""
    request = QueueRequestFactory(status=S.EXIT_CONFIRMED, pieces_total=5)
    release(request, 5)
    item = record(request, ExceptionKind.DAMAGE)
    other = record(request, ExceptionKind.SHORTAGE)

    boss.post(f"/api/exceptions/{item.pk}/resolve/", {"resolution": "Hal qilindi"}, format="json")
    assert QueueRequest.objects.get(pk=request.pk).status == S.EXIT_CONFIRMED  # one is still open
    boss.post(f"/api/exceptions/{other.pk}/resolve/", {"resolution": "Hal qilindi"}, format="json")
    assert QueueRequest.objects.get(pk=request.pk).status == S.CLOSED


def test_resolving_does_not_close_a_request_with_a_remainder(boss):
    request = QueueRequestFactory(status=S.EXIT_CONFIRMED, pieces_total=5)
    release(request, 3)
    item = record(request, ExceptionKind.DAMAGE)
    boss.post(f"/api/exceptions/{item.pk}/resolve/", {"resolution": "Hal qilindi"}, format="json")
    assert QueueRequest.objects.get(pk=request.pk).status == S.EXIT_CONFIRMED


def test_a_paused_warehouse_task_continues_where_it_stopped(boss):
    worker = client_for(UserFactory(role_code=R.WAREHOUSE, username="wh_exc"))
    task = create_task_for(QueueRequestFactory(status=S.REGISTERED))
    worker.post(f"/api/warehouse/tasks/{task.pk}/start/", {}, format="json")
    worker.post(
        f"/api/warehouse/tasks/{task.pk}/problem/",
        {"kind": "SHORTAGE", "description": "Kamomad"},
        format="json",
    )
    task.refresh_from_db()
    assert task.status == T.PROBLEM

    item = ExceptionRecord.objects.get(request=task.request)
    boss.post(f"/api/exceptions/{item.pk}/resolve/", {"resolution": "Topildi"}, format="json")
    task.refresh_from_db()
    assert task.status == T.IN_PROGRESS  # it had been started: it goes back to work
    assert worker.post(f"/api/warehouse/tasks/{task.pk}/ready/", format="json").status_code == 200


@pytest.mark.parametrize(
    ("started", "ready", "expected"),
    [(False, False, T.NEW), (True, False, T.IN_PROGRESS), (True, True, T.READY)],
)
def test_a_task_goes_back_to_the_state_it_was_in(boss, started, ready, expected):
    from django.utils import timezone

    request = QueueRequestFactory(status=S.AWAITING_PREP)
    task = WarehouseTask.objects.create(
        request=request,
        status=T.PROBLEM,
        started_at=timezone.now() if started else None,
        ready_at=timezone.now() if ready else None,
    )
    item = record(request, ExceptionKind.MISSING)
    boss.post(f"/api/exceptions/{item.pk}/resolve/", {"resolution": "Ok"}, format="json")
    task.refresh_from_db()
    assert task.status == expected


def test_the_task_stays_paused_while_another_warehouse_problem_is_open(boss):
    request = QueueRequestFactory(status=S.AWAITING_PREP)
    task = WarehouseTask.objects.create(request=request, status=T.PROBLEM)
    first = record(request, ExceptionKind.MISSING)
    record(request, ExceptionKind.DAMAGE)
    boss.post(f"/api/exceptions/{first.pk}/resolve/", {"resolution": "Ok"}, format="json")
    task.refresh_from_db()
    assert task.status == T.PROBLEM


# --- resuming a suspended request ------------------------------------------------------------------------------


def test_the_supervisor_resumes_a_suspended_request_to_where_it_was(boss):
    request = QueueRequestFactory(status=S.CARGO_READY)
    transition(request, S.SUSPENDED, UserFactory(role_code=R.SUPERVISOR, username="s2"), "Kutish")
    response = boss.post(f"/api/requests/{request.pk}/resume/", {"reason": "Davom"}, format="json")
    assert response.status_code == 200 and response.json()["status"] == S.CARGO_READY


def test_resume_needs_a_reason_and_a_suspended_request(boss):
    suspended = QueueRequestFactory(status=S.CARGO_READY)
    transition(suspended, S.SUSPENDED, UserFactory(role_code=R.SUPERVISOR, username="s3"), "Kutish")
    assert boss.post(f"/api/requests/{suspended.pk}/resume/", {}, format="json").status_code == 400
    active = QueueRequestFactory(status=S.CARGO_READY)
    response = boss.post(f"/api/requests/{active.pk}/resume/", {"reason": "x"}, format="json")
    assert response.status_code == 409 and response.json()["code"] == "not_suspended"

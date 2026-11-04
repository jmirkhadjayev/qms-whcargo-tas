"""Full and partial release at the dock (TZ 5.2)."""

import decimal

import pytest

from accounts.roles import RoleCode as R
from audit.models import AuditAction, AuditLog
from cargo_queue.models import QueueRequest, RequestStatusHistory
from cargo_queue.services.state_machine import transition
from cargo_queue.statuses import RequestStatus as S
from cargo_queue.tests.factories import DockFactory, UserFactory, make_dock_ready
from docks import errors
from docks.models import DockCategory, DockState, ReleaseOperation
from docks.tests.conftest import arrived_request, assigned, client_for, releasing_request
from exceptions_app.models import ExceptionKind, ExceptionRecord

pytestmark = [pytest.mark.django_db, pytest.mark.postgres]


def agent(dock):
    return client_for(dock.current_agent)


def url(request, action):
    return f"/api/requests/{request.pk}/release/{action}/"


def history(request):
    return list(
        RequestStatusHistory.objects.filter(request=request).values_list("to_status", flat=True)
    )


# --- starting ---------------------------------------------------------------------------------


def test_start_opens_a_release_operation(dock, supervisor):
    request = arrived_request(dock, supervisor, pieces_total=10)
    response = agent(dock).post(url(request, "start"))
    assert response.status_code == 200 and response.json()["status"] == S.RELEASE_STARTED
    operation = ReleaseOperation.objects.get(request=request)
    assert (operation.dock, operation.agent) == (dock, dock.current_agent)
    assert operation.pieces_released == 0 and operation.finished_at is None
    assert history(request)[-1] == S.RELEASE_STARTED


def test_only_the_agent_of_that_dock_may_start(dock, supervisor):
    request = arrived_request(dock, supervisor)
    other = make_dock_ready(DockFactory(code="D-02"), "other_agent")
    response = agent(other).post(url(request, "start"))
    assert response.status_code == 403 and response.json()["code"] == "not_your_dock"
    assert not ReleaseOperation.objects.exists()


def test_the_customer_must_have_arrived(dock, supervisor):
    make_dock_ready(dock)
    request = assigned(dock, supervisor)  # DOCK_ASSIGNED
    response = agent(dock).post(url(request, "start"))
    assert response.status_code == 409 and response.json()["code"] == "invalid_transition"


# --- counting pieces ------------------------------------------------------------------------------


def test_the_agent_counts_the_pieces_handed_over(dock, supervisor):
    request = releasing_request(dock, supervisor, pieces_total=10)
    response = agent(dock).post(url(request, "progress"), {"pieces_released": 4}, format="json")
    assert response.status_code == 200
    assert ReleaseOperation.objects.get(request=request).pieces_released == 4
    entry = AuditLog.objects.filter(entity="release_operations", action=AuditAction.UPDATE).latest(
        "id"
    )
    assert entry.old_value == {"pieces_released": 0} and entry.new_value == {"pieces_released": 4}
    agent(dock).post(url(request, "progress"), {"pieces_released": 3}, format="json")  # corrections
    assert ReleaseOperation.objects.get(request=request).pieces_released == 3


def test_more_pieces_than_exist_cannot_be_recorded(dock, supervisor):
    request = releasing_request(dock, supervisor, pieces_total=10)
    response = agent(dock).post(url(request, "progress"), {"pieces_released": 11}, format="json")
    assert response.status_code == 409 and response.json()["detail"] == errors.RELEASE_EXCEEDS
    assert ReleaseOperation.objects.get(request=request).pieces_released == 0


def test_negative_counts_are_refused(dock, supervisor):
    request = releasing_request(dock, supervisor)
    response = agent(dock).post(url(request, "progress"), {"pieces_released": -1}, format="json")
    assert response.status_code == 400 and "pieces_released" in response.json()


def test_counting_needs_a_started_release(dock, supervisor):
    request = arrived_request(dock, supervisor)
    response = agent(dock).post(url(request, "progress"), {"pieces_released": 1}, format="json")
    assert response.status_code == 409 and response.json()["code"] == "release_not_started"


# --- finishing: everything handed over ------------------------------------------------------------


def test_finishing_needs_every_piece(dock, supervisor):
    request = releasing_request(dock, supervisor, pieces_total=10)
    agent(dock).post(url(request, "progress"), {"pieces_released": 9}, format="json")
    response = agent(dock).post(url(request, "finish"), {}, format="json")
    assert response.status_code == 409 and response.json()["code"] == "release_incomplete"
    request.refresh_from_db()
    assert request.status == S.RELEASE_STARTED
    assert ReleaseOperation.objects.get(request=request).finished_at is None  # rolled back


def test_full_release_goes_on_to_the_checkpoint(dock, supervisor):
    request = releasing_request(dock, supervisor, pieces_total=10, weight_kg=200)
    agent(dock).post(url(request, "progress"), {"pieces_released": 10}, format="json")
    response = agent(dock).post(url(request, "finish"), {}, format="json")
    assert response.status_code == 200 and response.json()["status"] == S.AWAITING_CHECKPOINT

    assert history(request)[-2:] == [S.RELEASED, S.AWAITING_CHECKPOINT]
    steps = RequestStatusHistory.objects.filter(request=request).order_by("-id")[:2]
    assert [h.changed_by_id is None for h in steps] == [True, False]  # the system moves it on
    operation = ReleaseOperation.objects.get(request=request)
    assert operation.finished_at is not None
    assert operation.weight_released_kg == decimal.Decimal("200.00")
    dock.refresh_from_db()
    assert dock.state == DockState.FREE  # the dock is free for the next customer


def test_the_weight_follows_the_pieces_unless_the_agent_weighs(dock, supervisor):
    request = releasing_request(dock, supervisor, pieces_total=8, weight_kg=100)
    agent(dock).post(url(request, "progress"), {"pieces_released": 8}, format="json")
    agent(dock).post(url(request, "finish"), {"weight_released_kg": "98.50"}, format="json")
    assert ReleaseOperation.objects.get(request=request).weight_released_kg == decimal.Decimal(
        "98.50"
    )


# --- finishing: part of the cargo ---------------------------------------------------------------------


def partial(dock, request, reason="DAMAGE", comment="Ikki quti ezilgan"):
    return agent(dock).post(
        url(request, "partial"), {"reason": reason, "comment": comment}, format="json"
    )


def test_partial_release_records_everything_tz_5_2_asks_for(dock, supervisor):
    request = releasing_request(dock, supervisor, pieces_total=10)
    agent(dock).post(url(request, "progress"), {"pieces_released": 7}, format="json")
    response = partial(dock, request)
    assert response.status_code == 200 and response.json()["status"] == S.AWAITING_CHECKPOINT

    operation = ReleaseOperation.objects.get(request=request)
    assert operation.pieces_released == 7 and operation.finished_at is not None
    assert operation.agent == dock.current_agent  # who is responsible
    entry = RequestStatusHistory.objects.get(request=request, to_status=S.PARTIALLY_RELEASED)
    assert (
        entry.reason == "Yuk shikastlangan: Ikki quti ezilgan"
        and entry.changed_by == dock.current_agent
    )
    assert entry.changed_at is not None  # when
    record = ExceptionRecord.objects.get(request=request)
    assert (record.kind, record.pieces_affected, record.reported_by) == (
        ExceptionKind.PARTIAL,
        3,  # not handed over: 10 - 7
        dock.current_agent,
    )
    assert "Ikki quti ezilgan" in record.description and record.is_open
    assert history(request)[-2:] == [S.PARTIALLY_RELEASED, S.AWAITING_CHECKPOINT]


def test_the_request_stays_open_after_a_partial_release(dock, supervisor):
    request = releasing_request(dock, supervisor, pieces_total=10)
    agent(dock).post(url(request, "progress"), {"pieces_released": 7}, format="json")
    partial(dock, request)
    request.refresh_from_db()
    assert request.status not in (S.CLOSED, S.CANCELLED) and request.closed_at is None


@pytest.mark.parametrize(
    "body",
    [
        {"reason": "DAMAGE", "comment": ""},
        {"reason": "DAMAGE", "comment": "   "},
        {"reason": "DAMAGE"},
        {"reason": "NOPE", "comment": "x"},
        {"comment": "x"},
    ],
)
def test_partial_release_needs_a_reason_and_a_comment(dock, supervisor, body):
    request = releasing_request(dock, supervisor, pieces_total=10)
    agent(dock).post(url(request, "progress"), {"pieces_released": 7}, format="json")
    response = agent(dock).post(url(request, "partial"), body, format="json")
    assert response.status_code == 400
    request.refresh_from_db()
    assert request.status == S.RELEASE_STARTED and not ExceptionRecord.objects.exists()


def test_it_is_not_partial_when_everything_was_handed_over(dock, supervisor):
    request = releasing_request(dock, supervisor, pieces_total=10)
    agent(dock).post(url(request, "progress"), {"pieces_released": 10}, format="json")
    response = partial(dock, request)
    assert response.status_code == 409 and response.json()["code"] == "release_not_partial"


def test_a_partial_release_may_hand_over_nothing(dock, supervisor):
    request = releasing_request(dock, supervisor, pieces_total=4)
    response = partial(dock, request, "MISSING", "Yuk omborda topilmadi")
    assert response.status_code == 200
    assert ExceptionRecord.objects.get(request=request).pieces_affected == 4


@pytest.mark.parametrize("reason", list(errors.PARTIAL_REASONS))
def test_every_listed_reason_is_accepted(dock, supervisor, reason):
    request = releasing_request(dock, supervisor, pieces_total=5)
    response = partial(dock, request, reason, "Izoh")
    assert response.status_code == 200
    entry = RequestStatusHistory.objects.get(request=request, to_status=S.PARTIALLY_RELEASED)
    assert entry.reason == f"{errors.PARTIAL_REASONS[reason]}: Izoh"


# --- problems at the dock ---------------------------------------------------------------------------------


def test_the_agent_reports_a_problem_without_changing_the_status(dock, supervisor):
    request = releasing_request(dock, supervisor, pieces_total=10)
    response = agent(dock).post(
        f"/api/requests/{request.pk}/problems/",
        {"kind": "DAMAGE", "description": "Quti ezilgan", "pieces_affected": 2},
        format="json",
    )
    assert response.status_code == 201 and response.json()["kind"] == "DAMAGE"
    record = ExceptionRecord.objects.get(request=request)
    assert (record.pieces_affected, record.reported_by) == (2, dock.current_agent)
    request.refresh_from_db()
    assert request.status == S.RELEASE_STARTED  # the SUPERVISOR decides (K16)
    assert AuditLog.objects.filter(entity="exceptions", entity_id=record.pk).exists()


def test_problem_validation_and_scope(dock, supervisor):
    request = releasing_request(dock, supervisor)
    ep = f"/api/requests/{request.pk}/problems/"
    bad_kind = agent(dock).post(ep, {"kind": "NO_SHOW", "description": "x"}, format="json")
    assert bad_kind.status_code == 400 and "kind" in bad_kind.json()
    no_text = agent(dock).post(ep, {"kind": "DAMAGE", "description": ""}, format="json")
    assert no_text.status_code == 400
    other = make_dock_ready(DockFactory(code="D-02"), "other_agent")
    refused = agent(other).post(ep, {"kind": "DAMAGE", "description": "x"}, format="json")
    assert refused.status_code == 403 and refused.json()["code"] == "not_your_dock"
    assert not ExceptionRecord.objects.exists()


def test_a_request_that_is_not_at_the_dock_has_no_dock_problems(dock, supervisor):
    request = releasing_request(dock, supervisor)
    agent(dock).post(url(request, "progress"), {"pieces_released": 0}, format="json")
    transition(request, S.SUSPENDED, supervisor, "Kutish")
    response = agent(dock).post(
        f"/api/requests/{request.pk}/problems/",
        {"kind": "DAMAGE", "description": "x"},
        format="json",
    )
    assert response.status_code == 409 and response.json()["code"] == "not_at_dock"


def test_the_supervisor_can_record_a_problem_for_any_request(dock, supervisor):
    request = arrived_request(dock, supervisor)
    response = client_for(supervisor).post(
        f"/api/requests/{request.pk}/problems/",
        {"kind": "MISMATCH", "description": "Hujjat nomuvofiq"},
        format="json",
    )
    assert response.status_code == 201


# --- the agent's screen ------------------------------------------------------------------------------------


def test_the_agent_screen_shows_what_has_been_released(dock, supervisor):
    request = releasing_request(dock, supervisor, pieces_total=10)
    agent(dock).post(url(request, "progress"), {"pieces_released": 6}, format="json")
    current = agent(dock).get("/api/dock/me/").json()["current"]
    assert current["status"] == S.RELEASE_STARTED
    assert (current["pieces_released"], current["pieces_remaining"]) == (6, 4)
    assert current["operation_pieces"] == 6


# --- the whole story: partial release, the remainder, closing -----------------------------------------------


def test_the_remainder_makes_a_second_round_and_the_request_closes_at_the_end(dock, supervisor):
    from cargo_queue.services import closing
    from warehouse.models import WarehouseTask

    DockCategory.objects.get_or_create(dock=dock, category=dock.dock_categories.get().category)
    boss = client_for(supervisor)
    request = releasing_request(dock, supervisor, pieces_total=10)

    # round 1: 7 of 10 pieces, the rest is damaged
    agent(dock).post(url(request, "progress"), {"pieces_released": 7}, format="json")
    partial(dock, request)
    officer = UserFactory(role_code=R.CHECKPOINT, username="cp_story")
    transition(request, S.EXIT_CONFIRMED, officer)  # the checkpoint lets the vehicle go
    assert closing.try_close(request.pk) is False  # a remainder: the system does not close
    request.refresh_from_db()
    assert request.status == S.EXIT_CONFIRMED

    # the supervisor sends the remainder through the warehouse again
    response = boss.post(
        f"/api/requests/{request.pk}/transition/", {"to_status": "AWAITING_PREP"}, format="json"
    )
    assert response.status_code == 200 and response.json()["dock"] is None
    new_task = WarehouseTask.objects.filter(request=request).latest("id")
    assert new_task.status == "NEW" and WarehouseTask.objects.filter(request=request).count() == 2

    # warehouse prepares the remainder, a dock is assigned, the customer comes back
    new_task.status = "READY"
    new_task.save()
    transition(request, S.PREP_STARTED, UserFactory(role_code=R.WAREHOUSE, username="wh_story"))
    transition(request, S.CARGO_READY, UserFactory(role_code=R.WAREHOUSE, username="wh_story"))
    transition(request, S.AWAITING_DOCK, None)
    transition(request, S.DOCK_ASSIGNED, supervisor, extra={"dock": "D-01"})
    from docks import calls

    assert calls.try_call(request)
    transition(request, S.ARRIVED, dock.current_agent)

    # round 2: the remaining 3 pieces
    agent(dock).post(url(request, "start"))
    assert closing.remaining_pieces(request) == 3
    too_many = agent(dock).post(url(request, "progress"), {"pieces_released": 4}, format="json")
    assert too_many.status_code == 409  # only the remainder is left to hand over
    agent(dock).post(url(request, "progress"), {"pieces_released": 3}, format="json")
    assert agent(dock).post(url(request, "finish"), {}, format="json").status_code == 200

    assert not ExceptionRecord.objects.filter(request=request, resolved_at__isnull=True).exists()
    assert closing.released_pieces(request) == 10
    transition(request, S.EXIT_CONFIRMED, officer)
    assert closing.try_close(request.pk) is True
    request.refresh_from_db()
    assert request.status == S.CLOSED and request.closed_at is not None
    assert ReleaseOperation.objects.filter(request=request).count() == 2


def test_a_remainder_can_be_closed_by_a_documented_decision(dock, supervisor):
    request = releasing_request(dock, supervisor, pieces_total=10)
    agent(dock).post(url(request, "progress"), {"pieces_released": 7}, format="json")
    partial(dock, request, "CUSTOMER", "Mijoz qolganini keyin oladi")
    transition(request, S.EXIT_CONFIRMED, UserFactory(role_code=R.CHECKPOINT, username="cp_dec"))

    boss = client_for(supervisor)
    refused = boss.post(
        f"/api/requests/{request.pk}/transition/", {"to_status": "CLOSED"}, format="json"
    )
    assert refused.status_code == 409 and refused.json()["code"] == "close_with_remainder"

    closed = boss.post(
        f"/api/requests/{request.pk}/transition/",
        {"to_status": "CLOSED", "reason": "Buyurtmachi bilan kelishildi"},
        format="json",
    )
    assert closed.status_code == 200 and closed.json()["status"] == S.CLOSED
    record = ExceptionRecord.objects.get(request=request)
    assert record.resolved_at is not None and record.resolution == "Buyurtmachi bilan kelishildi"
    assert record.resolved_by is not None


def test_an_open_discrepancy_still_blocks_closing_a_remainder(dock, supervisor):
    request = releasing_request(dock, supervisor, pieces_total=10)
    agent(dock).post(url(request, "progress"), {"pieces_released": 7}, format="json")
    partial(dock, request)
    ExceptionRecord.objects.create(request=request, kind=ExceptionKind.DAMAGE, description="x")
    transition(request, S.EXIT_CONFIRMED, UserFactory(role_code=R.CHECKPOINT, username="cp_blk"))
    refused = client_for(supervisor).post(
        f"/api/requests/{request.pk}/transition/",
        {"to_status": "CLOSED", "reason": "Qaror"},
        format="json",
    )
    assert refused.status_code == 409 and refused.json()["code"] == "open_exceptions"
    assert QueueRequest.objects.get(pk=request.pk).status == S.EXIT_CONFIRMED

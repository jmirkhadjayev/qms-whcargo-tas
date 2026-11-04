"""Calling customers to docks (TZ 3.3, 3.4) and the no-show timer (TZ 5.1)."""

import pytest
from django.utils import timezone

from accounts.roles import RoleCode as R
from audit.models import AuditLog
from cargo_queue.models import QueueRequest, RequestStatusHistory
from cargo_queue.services.state_machine import TransitionError, transition
from cargo_queue.statuses import RequestStatus as S
from cargo_queue.tests.factories import (
    DockFactory,
    QueueRequestFactory,
    UserFactory,
    make_cargo_ready,
    make_dock_ready,
)
from docks import calls, errors
from docks.models import CallEvent, CallOutcome, DockCategory, DockState
from docks.tasks import call_waiting_requests, process_no_shows
from docks.tests.conftest import age_call, assigned, client_for, set_setting
from exceptions_app.models import ExceptionKind, ExceptionRecord
from notifications.models import SmsMessage, SmsTemplate
from warehouse.models import WarehouseTask, WarehouseTaskStatus

pytestmark = [pytest.mark.django_db, pytest.mark.postgres]


def agent_client(dock):
    return client_for(dock.current_agent)


def history(request):
    return list(
        RequestStatusHistory.objects.filter(request=request).values_list("to_status", flat=True)
    )


# --- what must be ready before a customer is called -------------------------------------------


def test_nothing_missing_means_no_blockers(dock, supervisor):
    make_dock_ready(dock)
    request = assigned(dock, supervisor)
    assert calls.call_blockers(request) == []


@pytest.mark.parametrize(
    ("task_status", "blocked"),
    [
        (None, True),
        (WarehouseTaskStatus.NEW, True),
        (WarehouseTaskStatus.IN_PROGRESS, True),
        (WarehouseTaskStatus.PROBLEM, True),
        (WarehouseTaskStatus.READY, False),
        (WarehouseTaskStatus.HANDED_OVER, False),
    ],
)
def test_cargo_must_be_ready(dock, supervisor, task_status, blocked):
    make_dock_ready(dock)
    request = assigned(dock, supervisor, cargo_ready=False)
    if task_status:
        WarehouseTask.objects.create(request=request, status=task_status)
    assert (calls.call_blockers(request) == ["cargo_not_ready"]) is blocked


def test_dock_staff_must_be_ready(dock, supervisor):
    request = assigned(dock, supervisor)
    assert calls.call_blockers(request) == ["agent_not_ready"]


@pytest.mark.parametrize("change", [{"state": DockState.MAINTENANCE}, {"is_active": False}])
def test_dock_must_be_in_service(dock, supervisor, change):
    make_dock_ready(dock)
    request = assigned(dock, supervisor)
    type(dock).objects.filter(pk=dock.pk).update(**change)
    request.refresh_from_db()
    assert calls.call_blockers(request) == ["dock_unavailable"]


def test_every_missing_condition_is_reported(dock, supervisor):
    request = assigned(dock, supervisor, cargo_ready=False)
    type(dock).objects.filter(pk=dock.pk).update(state=DockState.MAINTENANCE)
    request.refresh_from_db()
    assert calls.call_blockers(request) == [
        "cargo_not_ready",
        "dock_unavailable",
        "agent_not_ready",
    ]


def test_the_state_machine_refuses_a_call_that_is_not_ready(dock, supervisor):
    request = assigned(dock, supervisor)  # no staff at the dock
    before = (RequestStatusHistory.objects.count(), SmsMessage.objects.count())
    for who in (None, supervisor):
        with pytest.raises(TransitionError) as err:
            transition(request, S.CALLED, who)
        assert err.value.code == "call_not_ready"
        assert err.value.extra["blockers"] == ["agent_not_ready"]
        assert errors.CALL_BLOCKERS["agent_not_ready"] in err.value.message
    request.refresh_from_db()
    assert request.status == S.DOCK_ASSIGNED
    assert not CallEvent.objects.exists()
    assert (RequestStatusHistory.objects.count(), SmsMessage.objects.count()) == before


# --- the call itself -------------------------------------------------------------------------


def test_automatic_call_when_everything_is_ready(dock, supervisor):
    make_dock_ready(dock)
    request = assigned(dock, supervisor)
    assert calls.try_call(request) is True
    request.refresh_from_db()
    assert request.status == S.CALLED
    event = CallEvent.objects.get(request=request)
    assert (event.attempt_no, event.outcome, event.dock) == (1, CallOutcome.PENDING, dock)
    assert event.called_by is None and event.arrived_at is None
    last = RequestStatusHistory.objects.filter(request=request).latest("id")
    assert (last.to_status, last.changed_by) == (S.CALLED, None)  # the system


def test_the_call_sends_the_customer_an_sms_with_number_and_dock(dock, supervisor):
    make_dock_ready(dock)
    request = assigned(dock, supervisor, queue_number=42)
    calls.try_call(request)
    sms = SmsMessage.objects.get(request=request, template=SmsTemplate.CALLED)
    assert sms.phone == request.sms_phone
    assert "42" in sms.body and "D-01" in sms.body


def test_try_call_waits_while_something_is_missing(dock, supervisor):
    request = assigned(dock, supervisor)
    assert calls.try_call(request) is False
    request.refresh_from_db()
    assert request.status == S.DOCK_ASSIGNED and not CallEvent.objects.exists()


def test_try_call_ignores_requests_that_are_not_waiting_for_a_call(dock, supervisor):
    make_dock_ready(dock)
    request = QueueRequestFactory(status=S.AWAITING_DOCK)
    assert calls.try_call(request) is False


def test_assigning_a_dock_calls_at_once_when_ready(dock, supervisor):
    make_dock_ready(dock)
    request = QueueRequestFactory(status=S.AWAITING_DOCK)
    make_cargo_ready(request)
    response = client_for(supervisor).post(
        f"/api/requests/{request.pk}/assign-dock/", {"dock": "D-01"}, format="json"
    )
    assert response.status_code == 200 and response.json()["status"] == S.CALLED


def test_assigning_a_dock_waits_when_staff_is_not_ready_then_the_check_in_calls(dock, supervisor):
    request = QueueRequestFactory(status=S.AWAITING_DOCK)
    make_cargo_ready(request)
    response = client_for(supervisor).post(
        f"/api/requests/{request.pk}/assign-dock/", {"dock": "D-01"}, format="json"
    )
    assert response.json()["status"] == S.DOCK_ASSIGNED

    agent = UserFactory(role_code=R.DOCK_AGENT, username="late_agent")
    assert (
        client_for(agent).post("/api/dock/checkin/", {"dock": "D-01"}, format="json").status_code
        == 200
    )
    request.refresh_from_db()
    assert request.status == S.CALLED


def test_the_periodic_job_calls_requests_that_became_ready(dock, supervisor):
    request = assigned(dock, supervisor)
    assert call_waiting_requests() == 0
    make_dock_ready(dock)
    assert call_waiting_requests() == 1
    request.refresh_from_db()
    assert request.status == S.CALLED
    assert call_waiting_requests() == 0


def test_supervisor_can_call_by_hand_and_is_told_what_is_missing(dock, supervisor):
    request = assigned(dock, supervisor)
    boss = client_for(supervisor)
    refused = boss.post(f"/api/requests/{request.pk}/call/")
    assert refused.status_code == 409
    body = refused.json()
    assert body["code"] == "call_not_ready" and body["blockers"] == ["agent_not_ready"]

    make_dock_ready(dock)
    done = boss.post(f"/api/requests/{request.pk}/call/")
    assert done.status_code == 200 and done.json()["status"] == S.CALLED
    assert CallEvent.objects.get(request=request).called_by == supervisor


# --- calling again -------------------------------------------------------------------------------


def called_request(dock, supervisor, **kwargs):
    make_dock_ready(dock)
    request = assigned(dock, supervisor, **kwargs)
    assert calls.try_call(request)
    return request


def test_recall_by_the_dock_agent(dock, supervisor):
    request = called_request(dock, supervisor)
    response = agent_client(dock).post(f"/api/requests/{request.pk}/recall/")
    assert response.status_code == 200 and response.json()["status"] == S.CALLED

    first, second = CallEvent.objects.filter(request=request).order_by("id")
    assert (first.attempt_no, first.outcome) == (1, CallOutcome.NO_SHOW)
    assert (second.attempt_no, second.outcome) == (2, CallOutcome.PENDING)
    assert second.called_by == dock.current_agent
    assert history(request)[-2:] == [S.CALLED, S.CALLED]
    recall_sms = SmsMessage.objects.get(request=request, template=SmsTemplate.RECALL)
    assert "D-01" in recall_sms.body and "10" in recall_sms.body  # the waiting time


def test_recall_count_is_limited_by_the_setting(dock, supervisor):
    set_setting("max_recalls", 1)
    request = called_request(dock, supervisor)
    agent = agent_client(dock)
    assert agent.post(f"/api/requests/{request.pk}/recall/").status_code == 200
    refused = agent.post(f"/api/requests/{request.pk}/recall/")
    assert refused.status_code == 409 and refused.json()["code"] == "recall_limit"
    assert CallEvent.objects.filter(request=request).count() == 2


def test_supervisor_may_recall_too(dock, supervisor):
    request = called_request(dock, supervisor)
    assert client_for(supervisor).post(f"/api/requests/{request.pk}/recall/").status_code == 200


def test_a_dock_agent_cannot_act_on_another_docks_customer(dock, supervisor):
    request = called_request(dock, supervisor)
    other = make_dock_ready(DockFactory(code="D-02"), "other_agent")
    for action in ("recall", "arrive"):
        response = agent_client(other).post(f"/api/requests/{request.pk}/{action}/")
        assert response.status_code == 403 and response.json()["code"] == "not_your_dock"
    request.refresh_from_db()
    assert request.status == S.CALLED


def test_an_agent_who_is_not_at_a_dock_cannot_act(dock, supervisor):
    request = called_request(dock, supervisor)
    stray = UserFactory(role_code=R.DOCK_AGENT, username="stray")
    response = client_for(stray).post(f"/api/requests/{request.pk}/arrive/")
    assert response.status_code == 409 and response.json()["code"] == "agent_not_at_dock"


# --- arrival ---------------------------------------------------------------------------------------


def test_arrival_is_recorded(dock, supervisor):
    request = called_request(dock, supervisor)
    response = agent_client(dock).post(f"/api/requests/{request.pk}/arrive/")
    assert response.status_code == 200 and response.json()["status"] == S.ARRIVED
    event = CallEvent.objects.get(request=request)
    assert event.outcome == CallOutcome.ARRIVED and event.arrived_at is not None
    assert history(request)[-1] == S.ARRIVED


def test_arrival_needs_a_call_first(dock, supervisor):
    make_dock_ready(dock)
    request = assigned(dock, supervisor)  # DOCK_ASSIGNED, not called yet
    response = agent_client(dock).post(f"/api/requests/{request.pk}/arrive/")
    assert response.status_code == 409 and response.json()["code"] == "invalid_transition"


# --- the no-show timer -------------------------------------------------------------------------------


def test_nothing_happens_before_the_waiting_time_is_over(dock, supervisor):
    request = called_request(dock, supervisor)
    age_call(request, 9)
    assert process_no_shows() == {}
    request.refresh_from_db()
    assert request.status == S.CALLED and CallEvent.objects.filter(request=request).count() == 1


def test_the_waiting_time_comes_from_the_settings(dock, supervisor):
    set_setting("no_show_timeout_min", 30)
    request = called_request(dock, supervisor)
    age_call(request, 20)
    assert process_no_shows() == {}
    age_call(request, 31)
    assert process_no_shows() == {"recalled": 1}


def test_unanswered_call_is_repeated(dock, supervisor):
    request = called_request(dock, supervisor)
    age_call(request, 11)
    assert process_no_shows() == {"recalled": 1}
    request.refresh_from_db()
    assert request.status == S.CALLED
    assert CallEvent.objects.filter(request=request).count() == 2
    assert SmsMessage.objects.filter(request=request, template=SmsTemplate.RECALL).count() == 1
    assert process_no_shows() == {}  # the new call has just been made: not due again


def test_after_the_last_recall_the_customer_goes_to_the_end_of_the_queue(dock, supervisor):
    set_setting("max_recalls", 1)
    request = called_request(dock, supervisor)
    old_sort = timezone.now() - timezone.timedelta(hours=1)
    QueueRequest.objects.filter(pk=request.pk).update(sort_at=old_sort)

    age_call(request, 11)
    assert process_no_shows() == {"recalled": 1}
    age_call(request, 11)
    assert process_no_shows() == {"requeued": 1}

    request.refresh_from_db()
    dock.refresh_from_db()
    assert request.status == S.AWAITING_DOCK and request.dock is None
    assert request.sort_at > old_sort and request.queue_number  # the ticket number stays
    assert dock.state == DockState.FREE
    assert set(CallEvent.objects.filter(request=request).values_list("outcome", flat=True)) == {
        CallOutcome.NO_SHOW
    }
    exception = ExceptionRecord.objects.get(request=request)
    assert exception.kind == ExceptionKind.NO_SHOW and exception.is_open
    sms = SmsMessage.objects.filter(request=request, template=SmsTemplate.STATUS).get()
    assert "navbat oxiriga" in sms.body
    last = RequestStatusHistory.objects.filter(request=request).latest("id")
    assert (last.from_status, last.to_status, last.changed_by) == (S.CALLED, S.AWAITING_DOCK, None)


def test_a_customer_who_comes_after_being_requeued_clears_the_no_show(dock, supervisor):
    set_setting("max_recalls", 0)
    request = called_request(dock, supervisor)
    age_call(request, 11)
    assert process_no_shows() == {"requeued": 1}
    assert ExceptionRecord.objects.get(request=request).is_open

    # a second round: dock again, call again, and this time the customer arrives
    request.refresh_from_db()
    transition(request, S.DOCK_ASSIGNED, supervisor, extra={"dock": "D-01"})
    calls.try_call(request)
    assert calls.recalls_used(request) == 0  # a fresh round starts with fresh recalls
    assert agent_client(dock).post(f"/api/requests/{request.pk}/arrive/").status_code == 200
    assert not ExceptionRecord.objects.get(request=request).is_open


def test_the_second_no_show_cancels_when_only_one_requeue_is_allowed(dock, supervisor):
    set_setting("max_recalls", 0)
    set_setting("max_requeues", 1)
    request = called_request(dock, supervisor)
    age_call(request, 11)
    assert process_no_shows() == {"requeued": 1}

    request.refresh_from_db()
    transition(request, S.DOCK_ASSIGNED, supervisor, extra={"dock": "D-01"})
    calls.try_call(request)
    age_call(request, 11)
    assert process_no_shows() == {"cancelled": 1}

    request.refresh_from_db()
    assert request.status == S.CANCELLED
    last = RequestStatusHistory.objects.filter(request=request).latest("id")
    assert last.changed_by is None and "Kelmaslik" in last.reason
    assert not ExceptionRecord.objects.filter(request=request, resolved_at__isnull=True).exists()
    assert SmsMessage.objects.filter(request=request, body__contains="bekor qilindi").exists()
    # the history is kept (rule 3): nothing was deleted
    assert history(request).count(S.CALLED) == 2


def test_cancel_action_skips_the_requeue(dock, supervisor):
    set_setting("max_recalls", 0)
    set_setting("no_show_action", "CANCEL")
    request = called_request(dock, supervisor)
    age_call(request, 11)
    assert process_no_shows() == {"cancelled": 1}
    request.refresh_from_db()
    assert request.status == S.CANCELLED


def test_a_suspended_request_is_not_timed(dock, supervisor):
    request = called_request(dock, supervisor)
    transition(request, S.SUSPENDED, supervisor, "Tekshiruv")
    age_call(request, 60)
    assert process_no_shows() == {}
    request.refresh_from_db()
    assert request.status == S.SUSPENDED


def test_a_customer_who_arrived_is_left_alone(dock, supervisor):
    request = called_request(dock, supervisor)
    agent_client(dock).post(f"/api/requests/{request.pk}/arrive/")
    age_call(request, 60)
    assert process_no_shows() == {}


def test_a_call_answered_while_the_timer_runs_is_skipped(dock, supervisor):
    request = called_request(dock, supervisor)
    age_call(request, 11)
    transition(request, S.ARRIVED, dock.current_agent)  # arrived just before the timer looked
    assert calls.process_no_shows() == {}


# --- dock staff -------------------------------------------------------------------------------------


def test_check_in_makes_the_dock_ready_and_is_audited(dock):
    agent = UserFactory(role_code=R.DOCK_AGENT, username="ag1")
    response = client_for(agent).post("/api/dock/checkin/", {"dock": "d-01"}, format="json")
    assert response.status_code == 200 and response.json()["dock"]["code"] == "D-01"
    dock.refresh_from_db()
    assert dock.current_agent == agent and dock.agent_ready_at is not None
    assert AuditLog.objects.filter(entity="docks", entity_id=dock.pk).exists()


def test_a_dock_has_one_agent_and_an_agent_one_dock(dock):
    second = DockFactory(code="D-02")
    first_agent = UserFactory(role_code=R.DOCK_AGENT, username="ag1")
    other_agent = UserFactory(role_code=R.DOCK_AGENT, username="ag2")
    one, other = client_for(first_agent), client_for(other_agent)
    one.post("/api/dock/checkin/", {"dock": "D-01"}, format="json")

    taken = other.post("/api/dock/checkin/", {"dock": "D-01"}, format="json")
    assert taken.status_code == 409 and taken.json()["code"] == "dock_has_agent"

    assert one.post("/api/dock/checkin/", {"dock": "D-02"}, format="json").status_code == 200
    dock.refresh_from_db()
    second.refresh_from_db()
    assert dock.current_agent is None and dock.agent_ready_at is None
    assert second.current_agent == first_agent


def test_check_in_refusals(dock):
    agent = client_for(UserFactory(role_code=R.DOCK_AGENT, username="ag1"))
    assert agent.post("/api/dock/checkin/", {"dock": "D-77"}, format="json").status_code == 404
    type(dock).objects.filter(pk=dock.pk).update(state=DockState.MAINTENANCE)
    refused = agent.post("/api/dock/checkin/", {"dock": "D-01"}, format="json")
    assert refused.status_code == 409 and refused.json()["code"] == "dock_unavailable"


def test_check_out_is_blocked_while_a_customer_is_at_the_dock(dock, supervisor):
    request = called_request(dock, supervisor)
    agent = agent_client(dock)
    blocked = agent.post("/api/dock/checkout/")
    assert blocked.status_code == 409 and blocked.json()["code"] == "checkout_blocked"

    transition(request, S.CANCELLED, supervisor, "Bekor")
    done = agent.post("/api/dock/checkout/")
    assert done.status_code == 200 and done.json()["dock"] is None
    dock.refresh_from_db()
    assert dock.current_agent is None


# --- the dock agent's screen ----------------------------------------------------------------------------


def test_screen_before_check_in_offers_the_free_docks(dock):
    taken = make_dock_ready(DockFactory(code="D-02"), "someone")
    DockFactory(code="D-03", state=DockState.MAINTENANCE)
    agent = client_for(UserFactory(role_code=R.DOCK_AGENT, username="ag1"))
    body = agent.get("/api/dock/me/").json()
    assert body["dock"] is None and body["current"] is None
    assert [d["code"] for d in body["available_docks"]] == ["D-01"]
    assert taken.code not in [d["code"] for d in body["available_docks"]]


def test_screen_shows_the_current_customer_countdown_and_queue(dock, supervisor):
    request = called_request(dock, supervisor, queue_number=7, vehicle_plate="01A123BC")
    later = QueueRequestFactory(status=S.AWAITING_DOCK, queue_number=8, priority=3)
    body = agent_client(dock).get("/api/dock/me/").json()

    assert body["dock"]["code"] == "D-01" and body["dock"]["ready_since"]
    current = body["current"]
    assert current["id"] == request.pk and current["queue_number"] == 7
    assert current["status"] == S.CALLED and current["attempt_no"] == 1
    assert current["recalls_left"] == 2 and current["vehicle_plate"] == "01A123BC"
    assert current["timeout_at"] is not None and current["blockers"] == []
    assert [h["to_status"] for h in current["history"]][0] == S.CALLED
    assert [n["queue_number"] for n in body["next"]] == [later.queue_number]


def test_screen_explains_why_a_request_is_not_called_yet(dock, supervisor):
    request = assigned(dock, supervisor)  # nobody at the dock
    make_dock_ready(DockFactory(code="D-09"))
    agent_user = UserFactory(role_code=R.DOCK_AGENT, username="ag_blocked")
    client_for(agent_user).post("/api/dock/checkin/", {"dock": "D-09"}, format="json")
    assert request.status == S.DOCK_ASSIGNED


def test_scan_finds_only_the_customer_of_my_dock(dock, supervisor):
    request = called_request(dock, supervisor, queue_number=21)
    other_dock = make_dock_ready(DockFactory(code="D-02"), "ag_other")
    DockCategory.objects.create(dock=other_dock, category=request.category)
    foreign = QueueRequestFactory(status=S.AWAITING_DOCK)
    make_cargo_ready(foreign)
    transition(foreign, S.DOCK_ASSIGNED, supervisor, extra={"dock": "D-02"})

    agent = agent_client(dock)
    for code in (request.qr_token, request.awb_number, request.awb_number.replace("-", ""), "21"):
        response = agent.get("/api/dock/scan/", {"code": code})
        assert response.status_code == 200 and response.json()["id"] == request.pk, code
    assert agent.get("/api/dock/scan/", {"code": foreign.qr_token}).status_code == 404
    assert agent.get("/api/dock/scan/").json()["code"] == "scan_empty"
    assert (
        agent_client(other_dock).get("/api/dock/scan/", {"code": request.qr_token}).status_code
        == 404
    )

    stray = client_for(UserFactory(role_code=R.DOCK_AGENT, username="stray"))
    assert stray.get("/api/dock/scan/", {"code": "21"}).json()["code"] == "agent_not_at_dock"


# --- dispatcher view of calls ----------------------------------------------------------------------------


def test_dispatcher_queue_shows_blockers_and_attempts(dock, supervisor):
    waiting = assigned(dock, supervisor, queue_number=1)  # no staff yet
    boss = client_for(supervisor)
    row = {r["queue_number"]: r for r in boss.get("/api/dispatcher/queue/").json()}[1]
    assert row["call_blockers"] == ["agent_not_ready"] and row["attempts"] == 0

    make_dock_ready(dock)
    calls.try_call(waiting)
    age_call(waiting, 11)
    process_no_shows()
    row = {r["queue_number"]: r for r in boss.get("/api/dispatcher/queue/").json()}[1]
    assert row["call_blockers"] == [] and row["attempts"] == 2 and row["recalls_left"] == 1


def test_dispatcher_dock_cards_show_the_agent(dock):
    make_dock_ready(dock)
    boss = client_for(UserFactory(role_code=R.SUPERVISOR, username="boss_k"))
    card = {c["code"]: c for c in boss.get("/api/dispatcher/overview/").json()["docks"]}["D-01"]
    assert card["agent"] and card["agent_ready"] is True


def test_no_show_records_do_not_count_as_open_problems(dock, supervisor):
    set_setting("max_recalls", 0)
    request = called_request(dock, supervisor)
    age_call(request, 11)
    process_no_shows()
    kpi = client_for(supervisor).get("/api/dispatcher/overview/").json()["kpi"]
    assert kpi["open_exceptions"] == 0
    assert (
        ExceptionRecord.objects.filter(kind=ExceptionKind.NO_SHOW, resolved_at__isnull=True).count()
        == 1
    )


def test_run_timers_command_does_one_pass_of_every_periodic_job(dock, supervisor, capsys):
    from django.core.management import call_command

    set_setting("max_recalls", 0)
    request = called_request(dock, supervisor)
    age_call(request, 11)
    call_command("run_timers", "--once")
    request.refresh_from_db()
    assert request.status == S.AWAITING_DOCK  # the no-show timer ran
    assert "no-shows" in capsys.readouterr().out

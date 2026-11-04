"""The checkpoint (NO‘P): scan, confirm the exit, or hold it on a discrepancy (TZ 5.4)."""

import pytest

from accounts.roles import RoleCode as R
from audit.models import AuditAction, AuditLog
from cargo_queue.models import QueueRequest, RequestStatusHistory
from cargo_queue.statuses import RequestStatus as S
from cargo_queue.tests.factories import QueueRequestFactory, UserFactory, release
from checkpoint import errors
from checkpoint.models import CheckpointPass, CheckpointResult
from docks.tests.conftest import client_for
from exceptions_app.models import ExceptionKind, ExceptionRecord

pytestmark = [pytest.mark.django_db, pytest.mark.postgres]


@pytest.fixture
def officer_user():
    return UserFactory(role_code=R.CHECKPOINT, username="officer")


@pytest.fixture
def officer(officer_user):
    return client_for(officer_user)


@pytest.fixture
def boss():
    return client_for(UserFactory(role_code=R.SUPERVISOR, username="boss_cp"))


def waiting(released=10, total=10, **kwargs):
    """A vehicle at the checkpoint: the release is over."""
    request = QueueRequestFactory(
        status=S.AWAITING_CHECKPOINT, pieces_total=total, vehicle_plate="01A123BC", **kwargs
    )
    if released:
        release(request, released)
    return request


def statuses(request):
    return list(
        RequestStatusHistory.objects.filter(request=request).values_list("to_status", flat=True)
    )


# --- scanning -----------------------------------------------------------------------------------


def test_scan_shows_what_the_officer_checks(officer):
    request = waiting(released=7, total=10, queue_number=33)
    for code in (request.qr_token, request.awb_number, request.awb_number.replace("-", ""), "33"):
        response = officer.get("/api/checkpoint/scan/", {"code": code})
        assert response.status_code == 200, code
        body = response.json()
        assert body["id"] == request.pk and body["queue_number"] == 33
        assert (body["pieces_total"], body["pieces_released"], body["pieces_remaining"]) == (
            10,
            7,
            3,
        )
        assert body["vehicle_plate"] == "01A123BC" and body["can_confirm"] is True


def test_scan_errors(officer):
    assert officer.get("/api/checkpoint/scan/", {"code": "nothing"}).status_code == 404
    empty = officer.get("/api/checkpoint/scan/")
    assert empty.status_code == 400 and empty.json()["code"] == "scan_empty"


@pytest.mark.parametrize(
    "status",
    [
        S.CALLED,
        S.ARRIVED,
        S.RELEASE_STARTED,
        S.SUSPENDED,
        S.EXIT_CONFIRMED,
        S.CLOSED,
        S.CANCELLED,
    ],
)
def test_a_vehicle_that_is_not_waiting_is_explained(officer, status):
    request = QueueRequestFactory(status=status)
    body = officer.get("/api/checkpoint/scan/", {"code": request.qr_token}).json()
    assert body["can_confirm"] is False
    assert body["blocked_reason"] == errors.NOT_AWAITING[status]
    refused = officer.post(f"/api/checkpoint/{request.pk}/confirm/", {}, format="json")
    assert refused.status_code == 409 and refused.json()["code"] == "not_awaiting_checkpoint"
    assert QueueRequest.objects.get(pk=request.pk).status == status


def test_scan_lists_the_open_problems_of_the_request(officer):
    request = waiting(released=7, total=10)
    ExceptionRecord.objects.create(
        request=request, kind=ExceptionKind.PARTIAL, description="Qisman"
    )
    ExceptionRecord.objects.create(request=request, kind=ExceptionKind.NO_SHOW, description="x")
    body = officer.get("/api/checkpoint/scan/", {"code": request.qr_token}).json()
    assert [p["kind"] for p in body["open_problems"]] == ["PARTIAL"]  # "did not come" is no problem


# --- confirming the exit ------------------------------------------------------------------------


def test_exit_is_confirmed_and_the_request_closes_when_all_is_in_order(officer, officer_user):
    request = waiting()
    response = officer.post(
        f"/api/checkpoint/{request.pk}/confirm/", {"plate_observed": "01 a 123 bc"}, format="json"
    )
    assert response.status_code == 200
    request.refresh_from_db()
    assert request.status == S.CLOSED and request.closed_at is not None
    assert statuses(request)[-2:] == [S.EXIT_CONFIRMED, S.CLOSED]
    passed = CheckpointPass.objects.get(request=request)
    assert passed.officer == officer_user and passed.result == CheckpointResult.APPROVED
    assert passed.plate_observed == "01A123BC" and passed.exit_confirmed_at is not None
    closing_step = RequestStatusHistory.objects.filter(request=request).latest("id")
    assert closing_step.changed_by is None  # the system closed it


def test_a_remainder_keeps_the_request_open_after_the_exit(officer):
    request = waiting(released=7, total=10)
    officer.post(f"/api/checkpoint/{request.pk}/confirm/", {}, format="json")
    request.refresh_from_db()
    assert request.status == S.EXIT_CONFIRMED and request.closed_at is None  # TZ 5.2


def test_an_open_exception_keeps_the_request_open_after_the_exit(officer):
    request = waiting()
    ExceptionRecord.objects.create(request=request, kind=ExceptionKind.DAMAGE, description="x")
    officer.post(f"/api/checkpoint/{request.pk}/confirm/", {}, format="json")
    request.refresh_from_db()
    assert request.status == S.EXIT_CONFIRMED  # TZ 11 item 11: no automatic closing


def test_a_different_plate_is_a_discrepancy_not_a_confirmation(officer):
    request = waiting()
    response = officer.post(
        f"/api/checkpoint/{request.pk}/confirm/", {"plate_observed": "01B999ZZ"}, format="json"
    )
    assert response.status_code == 409 and response.json()["detail"] == errors.PLATE_MISMATCH
    assert QueueRequest.objects.get(pk=request.pk).status == S.AWAITING_CHECKPOINT
    assert not CheckpointPass.objects.exists()


def test_any_plate_is_fine_when_the_request_has_none(officer):
    request = QueueRequestFactory(status=S.AWAITING_CHECKPOINT, vehicle_plate="")
    release(request, request.pieces_total)
    response = officer.post(
        f"/api/checkpoint/{request.pk}/confirm/", {"plate_observed": "01C111DD"}, format="json"
    )
    assert response.status_code == 200


def test_the_confirmation_is_audited(officer):
    request = waiting()
    officer.post(f"/api/checkpoint/{request.pk}/confirm/", {}, format="json")
    assert AuditLog.objects.filter(
        action=AuditAction.TRANSITION, entity_id=request.pk, new_value__status=S.EXIT_CONFIRMED
    ).exists()


# --- holding the exit ----------------------------------------------------------------------------


def hold(officer, request, description="Yuk soni mos kelmadi", plate=""):
    return officer.post(
        f"/api/checkpoint/{request.pk}/hold/",
        {"description": description, "plate_observed": plate},
        format="json",
    )


def test_a_discrepancy_stops_the_exit_and_is_recorded(officer, officer_user):
    request = waiting()
    response = hold(officer, request, plate="01B999ZZ")
    assert response.status_code == 200 and response.json()["status"] == S.SUSPENDED

    request.refresh_from_db()
    assert request.status == S.SUSPENDED and request.closed_at is None
    record = ExceptionRecord.objects.get(request=request)
    assert record.kind == ExceptionKind.CHECKPOINT and record.is_open
    assert record.reported_by == officer_user and "01B999ZZ" in record.description
    held = CheckpointPass.objects.get(request=request)
    assert held.result == CheckpointResult.HELD and held.exit_confirmed_at is None
    assert held.plate_observed == "01B999ZZ"
    last = RequestStatusHistory.objects.filter(request=request).latest("id")
    assert (last.to_status, last.changed_by) == (S.SUSPENDED, officer_user)
    assert "Yuk soni mos kelmadi" in last.reason


def test_the_discrepancy_must_be_described(officer):
    request = waiting()
    for text in ("", "   "):
        response = hold(officer, request, text)
        assert response.status_code == 400
    request.refresh_from_db()
    assert request.status == S.AWAITING_CHECKPOINT and not ExceptionRecord.objects.exists()


def test_a_held_vehicle_cannot_be_confirmed(officer):
    request = waiting()
    hold(officer, request)
    again = officer.post(f"/api/checkpoint/{request.pk}/confirm/", {}, format="json")
    assert again.status_code == 409 and again.json()["detail"] == errors.NOT_AWAITING[S.SUSPENDED]


def test_the_system_does_not_close_a_held_request(officer):
    from cargo_queue.services import closing

    request = waiting()
    hold(officer, request)
    assert closing.try_close(request.pk) is False
    assert QueueRequest.objects.get(pk=request.pk).status == S.SUSPENDED


def test_the_exit_can_resume_only_after_the_supervisor_resolved_the_discrepancy(officer, boss):
    request = waiting()
    hold(officer, request)

    refused = boss.post(
        f"/api/requests/{request.pk}/resume/", {"reason": "Tekshirildi"}, format="json"
    )
    assert refused.status_code == 409 and refused.json()["code"] == "checkpoint_unresolved"

    record = ExceptionRecord.objects.get(request=request)
    resolved = boss.post(
        f"/api/exceptions/{record.pk}/resolve/",
        {"resolution": "Hujjatlar tekshirildi, o‘rinlar soni to‘g‘ri"},
        format="json",
    )
    assert resolved.status_code == 200

    resumed = boss.post(
        f"/api/requests/{request.pk}/resume/", {"reason": "Tafovut hal qilindi"}, format="json"
    )
    assert resumed.status_code == 200 and resumed.json()["status"] == S.AWAITING_CHECKPOINT

    # the officer checks again and this time lets the vehicle go
    assert (
        officer.post(f"/api/checkpoint/{request.pk}/confirm/", {}, format="json").status_code == 200
    )
    request.refresh_from_db()
    assert request.status == S.CLOSED
    assert (
        statuses(request)[-6:]
        == [
            S.SUSPENDED,
            S.AWAITING_CHECKPOINT,
            S.EXIT_CONFIRMED,
            S.CLOSED,
        ][-6:]
    )


# --- the tablet's lists --------------------------------------------------------------------------


def test_overview_lists_who_is_waiting_and_who_has_just_passed(officer):
    partial_one = waiting(released=7, total=10, queue_number=5)
    waiting(queue_number=6)
    done = waiting(queue_number=7)
    officer.post(f"/api/checkpoint/{done.pk}/confirm/", {}, format="json")
    held = waiting(queue_number=8)
    hold(officer, held)

    body = officer.get("/api/checkpoint/overview/").json()
    assert [(w["queue_number"], w["is_partial"]) for w in body["waiting"]] == [
        (5, True),
        (6, False),
    ]
    assert partial_one.pk == body["waiting"][0]["id"]
    assert [(r["queue_number"], r["result"]) for r in body["recent"]] == [
        (8, "HELD"),
        (7, "APPROVED"),
    ]
    assert all(r["officer"] for r in body["recent"])


def test_only_the_checkpoint_officer_may_use_it(boss):
    request = waiting()
    assert boss.get("/api/checkpoint/overview/").status_code == 403
    assert boss.post(f"/api/checkpoint/{request.pk}/confirm/", {}, format="json").status_code == 403


# --- acceptance (TZ 11) ----------------------------------------------------------------------------


def test_acceptance_a_discrepancy_blocks_the_usual_automatic_closing(officer):
    """TZ 11 item 11, end to end: with a discrepancy the request never closes by itself."""
    request = waiting()
    hold(officer, request)
    request.refresh_from_db()
    assert request.status != S.CLOSED
    assert ExceptionRecord.objects.filter(request=request, resolved_at__isnull=True).count() == 1

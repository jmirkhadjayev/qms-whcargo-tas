"""Domain rules 1-5 and 8 from CLAUDE.md, at service level and at database level."""

import datetime as dt
from pathlib import Path

import pytest
from django.conf import settings as django_settings
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from accounts.roles import RoleCode
from audit.append_only import AppendOnlyError
from audit.models import AuditAction, AuditLog
from cargo_queue.models import (
    PermitStatus,
    QueueRequest,
    RequestStatusHistory,
    StatusChangeNotAllowed,
)
from cargo_queue.services.registration import (
    DuplicateActiveRequest,
    PermitRejected,
    RegistrationData,
    register_request,
)
from cargo_queue.services.state_machine import transition
from cargo_queue.statuses import RequestStatus as S
from cargo_queue.tests.factories import (
    QueueRequestFactory,
    ReleasePermitFactory,
    UserFactory,
    release,
)

pytestmark = [pytest.mark.django_db, pytest.mark.postgres]


def reg_data(category, awb="176-12345670", **overrides) -> RegistrationData:
    values = {
        "awb_number": awb,
        "consignee_name": "Test MChJ",
        "sms_phone": "+998901234567",
        "pieces_total": 5,
        "weight_kg": 10,
        "category": category,
    }
    values.update(overrides)
    return RegistrationData(**values)


# --- rule 1: no request without a verified permit -----------------------------------------


def test_service_refuses_unverified_awb(shifts, category, reg_user):
    with pytest.raises(PermitRejected):
        register_request(reg_data(category, awb="176-12345671"), reg_user)  # odd -> rejected
    assert QueueRequest.objects.count() == 0


def test_service_refuses_malformed_awb(shifts, category, reg_user):
    with pytest.raises(PermitRejected):
        register_request(reg_data(category, awb="ABC"), reg_user)
    assert QueueRequest.objects.count() == 0


@pytest.mark.parametrize(
    ("permit_kwargs", "marker"),
    [
        ({"status": PermitStatus.INVALID}, "PERMIT_NOT_VERIFIED"),
        ({"status": PermitStatus.REVOKED}, "PERMIT_NOT_VERIFIED"),
        ({"valid_until": timezone.now() - dt.timedelta(days=1)}, "PERMIT_EXPIRED"),
    ],
)
def test_database_refuses_request_with_bad_permit(permit_kwargs, marker):
    permit = ReleasePermitFactory(**permit_kwargs)
    with pytest.raises(IntegrityError, match=marker), transaction.atomic():
        QueueRequestFactory(permit=permit)
    assert QueueRequest.objects.count() == 0


def test_database_refuses_request_whose_awb_differs_from_permit():
    permit = ReleasePermitFactory(awb_number="111-00000000")
    with pytest.raises(IntegrityError, match="PERMIT_AWB_MISMATCH"), transaction.atomic():
        QueueRequestFactory(permit=permit, awb_number="222-00000000")


def test_database_accepts_request_with_verified_permit():
    request = QueueRequestFactory()
    assert request.pk


def test_rejected_attempts_are_audited(shifts, category, reg_user):
    with pytest.raises(PermitRejected):
        register_request(reg_data(category, awb="176-12345671"), reg_user, ip="10.0.0.5")
    entry = AuditLog.objects.get(action=AuditAction.PERMIT_REJECTED)
    assert entry.user == reg_user
    assert entry.new_value["awb_number"] == "176-12345671"
    assert entry.ip_address == "10.0.0.5"


def test_duplicate_active_awb_refused_by_service_and_db(shifts, category, reg_user):
    register_request(reg_data(category), reg_user)
    with pytest.raises(DuplicateActiveRequest):
        register_request(reg_data(category), reg_user)

    first = QueueRequest.objects.get()
    other_permit = ReleasePermitFactory(awb_number=first.awb_number)
    with pytest.raises(IntegrityError, match="uq_active_request_per_awb"), transaction.atomic():
        QueueRequestFactory(permit=other_permit, queue_date=first.queue_date, queue_number=99)


def test_awb_can_be_registered_again_after_cancellation(shifts, category, reg_user):
    first = register_request(reg_data(category), reg_user)
    boss = UserFactory(role_code=RoleCode.SUPERVISOR, username="boss")
    transition(first, S.CANCELLED, boss, "Sabab")
    second = register_request(reg_data(category), reg_user)
    assert second.pk != first.pk and second.permit_id == first.permit_id


# --- rule 2: status changes only through the state machine --------------------------------


def test_status_cannot_be_assigned_and_saved():
    request = QueueRequestFactory()
    request.status = S.CLOSED
    with pytest.raises(StatusChangeNotAllowed):
        request.save()
    request.refresh_from_db()
    assert request.status == S.REGISTERED


def test_status_cannot_be_changed_by_queryset_update():
    request = QueueRequestFactory()
    with pytest.raises(StatusChangeNotAllowed):
        QueueRequest.objects.filter(pk=request.pk).update(status=S.CLOSED)
    with pytest.raises(StatusChangeNotAllowed):
        QueueRequest.objects.bulk_update([request], ["status"])


def test_other_fields_can_still_be_updated():
    request = QueueRequestFactory()
    request.notes = "yangi izoh"
    request.save()
    QueueRequest.objects.filter(pk=request.pk).update(priority=2)


def test_only_the_state_machine_uses_the_status_bypass_flag():
    root = Path(django_settings.BASE_DIR)
    offenders = []
    for path in root.rglob("*.py"):
        parts = path.relative_to(root).parts
        if (
            "tests" in parts
            or "migrations" in parts
            or ".venv" in parts
            or path.name == "models.py"
        ):
            continue
        if (
            "_status_change_allowed" in path.read_text(encoding="utf-8")
            and path.name != "state_machine.py"
        ):
            offenders.append(str(path))
    assert offenders == []


# --- rule 3: history is never changed or deleted ------------------------------------------


@pytest.fixture
def history_row():
    request = QueueRequestFactory()
    return RequestStatusHistory.objects.create(request=request, to_status=S.REGISTERED)


def test_history_orm_blocks_update_and_delete(history_row):
    history_row.reason = "x"
    with pytest.raises(AppendOnlyError):
        history_row.save()
    with pytest.raises(AppendOnlyError):
        history_row.delete()
    with pytest.raises(AppendOnlyError):
        RequestStatusHistory.objects.all().update(reason="x")
    with pytest.raises(AppendOnlyError):
        RequestStatusHistory.objects.all().delete()


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE request_status_history SET reason = 'x'",
        "DELETE FROM request_status_history",
    ],
)
def test_history_database_blocks_update_and_delete(history_row, sql):
    with (
        pytest.raises(IntegrityError, match="APPEND_ONLY"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(sql)
    assert RequestStatusHistory.objects.filter(pk=history_row.pk).exists()


@pytest.mark.parametrize("sql", ["UPDATE audit_log SET entity = 'x'", "DELETE FROM audit_log"])
def test_audit_database_blocks_update_and_delete(sql):
    AuditLog.objects.create(action=AuditAction.CREATE, entity="t")
    with (
        pytest.raises(IntegrityError, match="APPEND_ONLY"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(sql)
    assert AuditLog.objects.count() == 1


def test_audit_orm_blocks_update_and_delete():
    entry = AuditLog.objects.create(action=AuditAction.CREATE, entity="t")
    entry.entity = "x"
    with pytest.raises(AppendOnlyError):
        entry.save()
    with pytest.raises(AppendOnlyError):
        entry.delete()
    with pytest.raises(AppendOnlyError):
        AuditLog.objects.all().update(entity="x")


def test_requests_are_never_deleted():
    request = QueueRequestFactory()
    with pytest.raises(StatusChangeNotAllowed):
        request.delete()
    with (
        pytest.raises(IntegrityError, match="APPEND_ONLY"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute("DELETE FROM queue_requests")
    assert QueueRequest.objects.count() == 1


# --- rule 4: queue numbers -----------------------------------------------------------------


def test_numbers_are_sequential_and_restart_each_day(shifts, category, reg_user):
    tashkent = dt.timezone(dt.timedelta(hours=5))
    day1 = dt.datetime(2026, 11, 4, 10, 0, tzinfo=tashkent)
    day2 = dt.datetime(2026, 11, 5, 10, 0, tzinfo=tashkent)

    def register(awb, now):
        return register_request(reg_data(category, awb=awb), reg_user, now=now)

    a = register("176-00000010", day1)
    b = register("176-00000020", day1)
    c = register("176-00000030", day2)
    d = register("176-00000040", day2)
    assert [(r.queue_date.isoformat(), r.queue_number) for r in (a, b, c, d)] == [
        ("2026-11-04", 1),
        ("2026-11-04", 2),
        ("2026-11-05", 1),
        ("2026-11-05", 2),
    ]


def test_queue_date_uses_tashkent_time_not_utc(shifts, category, reg_user):
    # 20:00 UTC on 4 Nov is 01:00 on 5 Nov in Tashkent.
    now = dt.datetime(2026, 11, 4, 20, 0, tzinfo=dt.UTC)
    request = register_request(reg_data(category), reg_user, now=now)
    assert request.queue_date == dt.date(2026, 11, 5)


def test_duplicate_date_and_number_is_refused_by_the_database():
    first = QueueRequestFactory()
    with pytest.raises(IntegrityError, match="uq_queue_date_number"), transaction.atomic():
        QueueRequestFactory(queue_date=first.queue_date, queue_number=first.queue_number)


def test_rolled_back_registration_leaves_no_gap(shifts, category, reg_user, monkeypatch):
    register_request(reg_data(category, awb="176-00000010"), reg_user)

    def boom(*args, **kwargs):
        raise RuntimeError("printer on fire")

    monkeypatch.setattr("cargo_queue.services.registration.state_machine.record_creation", boom)
    with pytest.raises(RuntimeError):
        register_request(reg_data(category, awb="176-00000020"), reg_user)
    monkeypatch.undo()
    third = register_request(reg_data(category, awb="176-00000030"), reg_user)
    assert third.queue_number == 2


# --- rule 5: partial release ---------------------------------------------------------------


def test_released_pieces_cannot_exceed_total():
    request = QueueRequestFactory(pieces_total=10)
    release(request, 6)
    release(request, 4)
    with pytest.raises(IntegrityError, match="RELEASE_EXCEEDS_TOTAL"), transaction.atomic():
        release(request, 1)


def test_release_update_cannot_push_sum_over_total():
    request = QueueRequestFactory(pieces_total=10)
    op = release(request, 6)
    op.pieces_released = 11
    with pytest.raises(IntegrityError, match="RELEASE_EXCEEDS_TOTAL"), transaction.atomic():
        op.save()


def test_negative_release_is_refused():
    request = QueueRequestFactory()
    with pytest.raises(IntegrityError), transaction.atomic():
        release(request, -1)


# --- rule 8: time ---------------------------------------------------------------------------


def test_time_settings_and_timestamptz_columns():
    assert django_settings.TIME_ZONE == "Asia/Tashkent" and django_settings.USE_TZ
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name IN ('queue_requests', 'request_status_history', 'audit_log') "
            "AND column_name IN ('registered_at', 'closed_at', 'changed_at', 'created_at')"
        )
        rows = dict(cursor.fetchall())
    assert rows and set(rows.values()) == {"timestamp with time zone"}

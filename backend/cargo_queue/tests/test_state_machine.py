"""Every allowed transition, and many forbidden ones, against the table in CLAUDE.md."""

import datetime as dt

import pytest
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone

from accounts.roles import RoleCode as R
from audit.models import AuditAction, AuditLog
from cargo_queue.models import QueueRequest, RequestStatusHistory
from cargo_queue.services.state_machine import TransitionError, transition
from cargo_queue.statuses import PRE_RELEASE_STATUSES
from cargo_queue.statuses import RequestStatus as S
from cargo_queue.tests.factories import (
    DockFactory,
    QueueRequestFactory,
    UserFactory,
    make_callable,
    release,
)
from docks.models import DockCategory
from exceptions_app.models import ExceptionKind, ExceptionRecord

pytestmark = [pytest.mark.django_db, pytest.mark.postgres]

REASON = "Sabab matni"


def actor(role: R | None):
    return None if role is None else UserFactory(role_code=role, username=f"u_{role.value}")


def make_request(status: S, released: int | None = None) -> QueueRequest:
    request = QueueRequestFactory(status=status)
    if released:
        release(request, released)
    return request


def counts():
    return RequestStatusHistory.objects.count(), AuditLog.objects.count()


# (from, to, actor role or None for the system, reason, pieces released beforehand)
ALLOWED = [
    (S.REGISTERED, S.AWAITING_PREP, None, "", None),
    (S.AWAITING_PREP, S.PREP_STARTED, R.WAREHOUSE, "", None),
    (S.PREP_STARTED, S.CARGO_READY, R.WAREHOUSE, "", None),
    (S.CARGO_READY, S.AWAITING_DOCK, None, "", None),
    (S.AWAITING_DOCK, S.DOCK_ASSIGNED, R.SUPERVISOR, "", None),
    (S.DOCK_ASSIGNED, S.CALLED, R.SUPERVISOR, "", None),
    (S.DOCK_ASSIGNED, S.CALLED, None, "", None),
    (S.CALLED, S.CALLED, R.DOCK_AGENT, "", None),
    (S.CALLED, S.CALLED, None, "", None),
    (S.CALLED, S.ARRIVED, R.DOCK_AGENT, "", None),
    (S.CALLED, S.AWAITING_DOCK, R.DOCK_AGENT, "", None),
    (S.CALLED, S.AWAITING_DOCK, None, "", None),
    (S.CALLED, S.CANCELLED, R.DOCK_AGENT, REASON, None),
    (S.CALLED, S.CANCELLED, None, REASON, None),
    (S.ARRIVED, S.RELEASE_STARTED, R.DOCK_AGENT, "", None),
    (S.RELEASE_STARTED, S.RELEASED, R.DOCK_AGENT, "", 10),
    (S.RELEASE_STARTED, S.PARTIALLY_RELEASED, R.DOCK_AGENT, REASON, 6),
    (S.RELEASED, S.AWAITING_CHECKPOINT, None, "", None),
    (S.PARTIALLY_RELEASED, S.AWAITING_CHECKPOINT, None, "", 6),
    (S.AWAITING_CHECKPOINT, S.EXIT_CONFIRMED, R.CHECKPOINT, "", None),
    (S.AWAITING_CHECKPOINT, S.SUSPENDED, R.CHECKPOINT, REASON, None),
    (S.EXIT_CONFIRMED, S.CLOSED, None, "", 10),
    (S.EXIT_CONFIRMED, S.CLOSED, R.SUPERVISOR, "", 10),
    (S.EXIT_CONFIRMED, S.CLOSED, R.SUPERVISOR, REASON, 6),  # remainder closed by decision
    (S.EXIT_CONFIRMED, S.AWAITING_PREP, None, "", 6),
    (S.EXIT_CONFIRMED, S.AWAITING_PREP, R.SUPERVISOR, "", 6),
    (S.CLOSED, S.EXIT_CONFIRMED, R.ADMIN, REASON, None),
]
# Any non-final state -> SUSPENDED, and any pre-release state -> CANCELLED (SUPERVISOR).
ALLOWED += [
    (s, S.SUSPENDED, R.SUPERVISOR, REASON, None)
    for s in S
    if s not in (S.CLOSED, S.CANCELLED, S.SUSPENDED)
]
ALLOWED += [(s, S.CANCELLED, R.SUPERVISOR, REASON, None) for s in PRE_RELEASE_STATUSES]


@pytest.mark.parametrize(("frm", "to", "role", "reason", "released"), ALLOWED)
def test_allowed_transition(frm, to, role, reason, released):
    request = make_request(frm, released)
    user = actor(role)
    history_before, audit_before = counts()
    extra = None
    if (frm, to) in ((S.DOCK_ASSIGNED, S.CALLED), (S.CALLED, S.CALLED)):
        make_callable(request)  # a call needs cargo, dock and staff to be ready
    if (frm, to) == (S.AWAITING_DOCK, S.DOCK_ASSIGNED):
        # Assigning a dock needs the dock itself (and it must take this cargo category).
        dock = DockFactory(code="D-77")
        DockCategory.objects.create(dock=dock, category=request.category)
        extra = {"dock": dock.code}

    transition(request, to, user, reason or None, extra=extra)

    request.refresh_from_db()
    assert request.status == to
    last = RequestStatusHistory.objects.filter(request=request).latest("id")
    assert (last.from_status, last.to_status) == (frm, to)
    assert last.changed_by == user
    assert last.reason == reason
    assert counts() == (history_before + 1, audit_before + 1)
    entry = AuditLog.objects.latest("id")
    expected_action = (
        AuditAction.REOPEN if (frm, to) == (S.CLOSED, S.EXIT_CONFIRMED) else AuditAction.TRANSITION
    )
    assert (entry.action, entry.entity, entry.entity_id) == (
        expected_action,
        "queue_requests",
        request.pk,
    )
    assert entry.old_value == {"status": frm} and entry.new_value["status"] == to


def test_resume_goes_back_to_previous_status():
    request = make_request(S.ARRIVED)
    boss = actor(R.SUPERVISOR)
    transition(request, S.SUSPENDED, boss, REASON)
    transition(request, S.ARRIVED, boss, REASON)
    assert request.status == S.ARRIVED
    # and a second suspension resumes to where it was *then*
    transition(request, S.RELEASE_STARTED, actor(R.DOCK_AGENT))
    transition(request, S.SUSPENDED, boss, REASON)
    with pytest.raises(TransitionError) as err:
        transition(request, S.ARRIVED, boss, REASON)
    assert err.value.code == "resume_wrong_target"
    transition(request, S.RELEASE_STARTED, boss, REASON)


def test_suspended_can_be_cancelled_only_if_suspended_before_release():
    boss = actor(R.SUPERVISOR)
    early = make_request(S.CARGO_READY)
    transition(early, S.SUSPENDED, boss, REASON)
    transition(early, S.CANCELLED, boss, REASON)
    assert early.status == S.CANCELLED

    late = make_request(S.RELEASE_STARTED)
    transition(late, S.SUSPENDED, boss, REASON)
    with pytest.raises(TransitionError) as err:
        transition(late, S.CANCELLED, boss, REASON)
    assert err.value.code == "cancel_after_release"


def test_no_show_requeue_sends_request_to_end_of_queue_and_frees_dock():
    request = make_request(S.CALLED)
    request.dock = DockFactory(code="D-98")
    request.save(update_fields=["dock"])
    before = timezone.now() - dt.timedelta(hours=1)
    QueueRequest.objects.filter(pk=request.pk).update(sort_at=before)  # clock ticks can be coarse
    transition(request, S.AWAITING_DOCK, None)
    request.refresh_from_db()
    assert request.dock is None
    assert request.sort_at > before
    assert request.queue_number  # the printed number never changes


def test_second_cycle_for_remainder_requeues():
    request = make_request(S.EXIT_CONFIRMED, released=6)
    before = timezone.now() - dt.timedelta(hours=1)
    QueueRequest.objects.filter(pk=request.pk).update(sort_at=before)
    transition(request, S.AWAITING_PREP, None)
    request.refresh_from_db()
    assert request.sort_at > before


def test_closing_sets_and_reopening_clears_closed_at():
    request = make_request(S.EXIT_CONFIRMED, released=10)
    transition(request, S.CLOSED, None)
    request.refresh_from_db()
    assert request.closed_at is not None
    transition(request, S.EXIT_CONFIRMED, actor(R.ADMIN), REASON)
    request.refresh_from_db()
    assert request.closed_at is None


# --- forbidden ----------------------------------------------------------------------------

FORBIDDEN = [
    # not in the table at all
    (S.REGISTERED, S.CLOSED, R.SUPERVISOR, REASON, "invalid_transition"),
    (S.REGISTERED, S.REGISTERED, R.SUPERVISOR, REASON, "invalid_transition"),
    (S.CARGO_READY, S.CALLED, R.SUPERVISOR, REASON, "invalid_transition"),
    (S.ARRIVED, S.CARGO_READY, R.SUPERVISOR, REASON, "invalid_transition"),
    (S.CALLED, S.RELEASED, R.DOCK_AGENT, REASON, "invalid_transition"),
    (S.CANCELLED, S.AWAITING_PREP, R.SUPERVISOR, REASON, "invalid_transition"),
    (S.CANCELLED, S.SUSPENDED, R.SUPERVISOR, REASON, "invalid_transition"),
    (S.CLOSED, S.AWAITING_PREP, R.ADMIN, REASON, "invalid_transition"),
    (S.CLOSED, S.CANCELLED, R.ADMIN, REASON, "invalid_transition"),
    (S.SUSPENDED, S.SUSPENDED, R.SUPERVISOR, REASON, "invalid_transition"),
    (S.RELEASE_STARTED, S.CANCELLED, R.SUPERVISOR, REASON, "invalid_transition"),
    (S.AWAITING_CHECKPOINT, S.CANCELLED, R.SUPERVISOR, REASON, "invalid_transition"),
    # wrong actor
    (S.AWAITING_PREP, S.PREP_STARTED, R.REG_AGENT, "", "role_forbidden"),
    (S.AWAITING_PREP, S.PREP_STARTED, R.SUPERVISOR, "", "role_forbidden"),
    (S.AWAITING_PREP, S.PREP_STARTED, None, "", "role_forbidden"),  # the system cannot do this
    (S.AWAITING_DOCK, S.DOCK_ASSIGNED, R.WAREHOUSE, "", "role_forbidden"),
    (S.CALLED, S.ARRIVED, R.SUPERVISOR, "", "role_forbidden"),
    (S.AWAITING_CHECKPOINT, S.EXIT_CONFIRMED, R.DOCK_AGENT, "", "role_forbidden"),
    (S.ARRIVED, S.SUSPENDED, R.DOCK_AGENT, REASON, "role_forbidden"),
    (S.REGISTERED, S.AWAITING_PREP, R.SUPERVISOR, "", "role_forbidden"),  # system-only
    (S.CLOSED, S.EXIT_CONFIRMED, R.SUPERVISOR, REASON, "role_forbidden"),  # ADMIN only
    (S.ARRIVED, S.CANCELLED, R.MANAGER, REASON, "role_forbidden"),
    # reason missing
    (S.ARRIVED, S.CANCELLED, R.SUPERVISOR, "", "reason_required"),
    (S.ARRIVED, S.CANCELLED, R.SUPERVISOR, "   ", "reason_required"),
    (S.ARRIVED, S.SUSPENDED, R.SUPERVISOR, "", "reason_required"),
    (S.CLOSED, S.EXIT_CONFIRMED, R.ADMIN, "", "reason_required"),
    (S.CALLED, S.CANCELLED, None, "", "reason_required"),
    (S.AWAITING_CHECKPOINT, S.SUSPENDED, R.CHECKPOINT, "", "reason_required"),
]


@pytest.mark.parametrize(("frm", "to", "role", "reason", "code"), FORBIDDEN)
def test_forbidden_transition_changes_nothing(frm, to, role, reason, code):
    request = make_request(frm)
    user = actor(role)
    before = counts()
    with pytest.raises(TransitionError) as err:
        transition(request, to, user, reason)
    assert err.value.code == code
    request.refresh_from_db()
    assert request.status == frm
    assert counts() == before


def test_inactive_user_cannot_transition():
    request = make_request(S.AWAITING_PREP)
    user = actor(R.WAREHOUSE)
    user.is_active = False
    user.save()
    with pytest.raises(TransitionError) as err:
        transition(request, S.PREP_STARTED, user)
    assert err.value.code == "role_forbidden"


# --- guards -------------------------------------------------------------------------------


def expect_guard(frm, to, role, reason, code, released=None):
    request = make_request(frm, released)
    before = counts()
    with pytest.raises(TransitionError) as err:
        transition(request, to, actor(role), reason)
    assert err.value.code == code
    request.refresh_from_db()
    assert request.status == frm
    assert counts() == before


def test_released_requires_all_pieces():
    expect_guard(S.RELEASE_STARTED, S.RELEASED, R.DOCK_AGENT, "", "release_incomplete", 6)


def test_partially_released_requires_a_remainder():
    expect_guard(
        S.RELEASE_STARTED, S.PARTIALLY_RELEASED, R.DOCK_AGENT, REASON, "release_not_partial", 10
    )


def test_partial_release_needs_reason():
    expect_guard(S.RELEASE_STARTED, S.PARTIALLY_RELEASED, R.DOCK_AGENT, "", "reason_required", 6)


def test_remainder_cannot_be_closed_by_system_or_without_reason():
    expect_guard(S.EXIT_CONFIRMED, S.CLOSED, None, "", "close_with_remainder", 6)
    expect_guard(S.EXIT_CONFIRMED, S.CLOSED, R.SUPERVISOR, "", "close_with_remainder", 6)


def test_nothing_to_re_prepare_when_fully_released():
    expect_guard(S.EXIT_CONFIRMED, S.AWAITING_PREP, None, "", "no_remainder", 10)


def test_open_exception_blocks_closing():  # domain rule 6
    request = make_request(S.EXIT_CONFIRMED, released=10)
    record = ExceptionRecord.objects.create(request=request, kind=ExceptionKind.CHECKPOINT)
    before = counts()
    for who in (None, actor(R.SUPERVISOR)):
        with pytest.raises(TransitionError) as err:
            transition(request, S.CLOSED, who, REASON)
        assert err.value.code == "open_exceptions"
    assert counts() == before

    from django.utils import timezone

    record.resolved_at = timezone.now()
    record.save()
    transition(request, S.CLOSED, None)
    assert request.status == S.CLOSED


def test_resolved_exceptions_do_not_block_closing():
    from django.utils import timezone

    request = make_request(S.EXIT_CONFIRMED, released=10)
    ExceptionRecord.objects.create(
        request=request, kind=ExceptionKind.DAMAGE, resolved_at=timezone.now()
    )
    transition(request, S.CLOSED, None)
    assert request.status == S.CLOSED


# --- cross-cutting ------------------------------------------------------------------------


def test_every_transition_in_the_table_is_covered_by_an_allowed_case():
    from cargo_queue.services.state_machine import TRANSITIONS

    covered = {(str(f), str(t)) for f, t, *_ in ALLOWED}
    # Leaving SUSPENDED (resume / cancel) has its own dedicated tests above.
    missing = [key for key in TRANSITIONS if key not in covered and key[0] != S.SUSPENDED]
    assert missing == []


def test_event_is_sent_only_after_commit(django_capture_on_commit_callbacks):
    layer = get_channel_layer()
    channel = async_to_sync(layer.new_channel)()
    async_to_sync(layer.group_add)("dispatcher", channel)
    request = make_request(S.AWAITING_PREP)

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        transition(request, S.PREP_STARTED, actor(R.WAREHOUSE))
    # nothing was delivered yet: the callbacks run only after the real commit
    assert len(callbacks) == 1

    for callback in callbacks:
        callback()
    message = async_to_sync(layer.receive)(channel)
    assert message["request_id"] == request.pk
    assert (message["from_status"], message["to_status"]) == (S.AWAITING_PREP, S.PREP_STARTED)


def test_failed_transition_sends_no_event(django_capture_on_commit_callbacks):
    request = make_request(S.AWAITING_PREP)
    with (
        django_capture_on_commit_callbacks(execute=False) as callbacks,
        pytest.raises(TransitionError),
    ):
        transition(request, S.CLOSED, actor(R.SUPERVISOR), REASON)
    assert callbacks == []


def test_the_second_cycle_creates_a_fresh_warehouse_task_for_the_remainder():
    from warehouse.models import WarehouseTask, WarehouseTaskStatus

    request = make_request(S.EXIT_CONFIRMED, released=6)
    assert not WarehouseTask.objects.filter(request=request).exists()
    transition(request, S.AWAITING_PREP, None)
    task = WarehouseTask.objects.get(request=request)
    assert task.status == WarehouseTaskStatus.NEW and task.request == request


def test_closing_with_a_remainder_resolves_the_partial_record_with_the_decision():
    request = make_request(S.EXIT_CONFIRMED, released=6)
    partial = ExceptionRecord.objects.create(request=request, kind=ExceptionKind.PARTIAL)
    boss = actor(R.SUPERVISOR)
    transition(request, S.CLOSED, boss, "Mijoz bilan kelishildi")
    partial.refresh_from_db()
    assert partial.resolved_by == boss and partial.resolution == "Mijoz bilan kelishildi"


def test_the_exit_cannot_resume_while_a_checkpoint_discrepancy_is_open():
    request = make_request(S.AWAITING_CHECKPOINT)
    boss = actor(R.SUPERVISOR)
    transition(request, S.SUSPENDED, boss, REASON)
    record = ExceptionRecord.objects.create(request=request, kind=ExceptionKind.CHECKPOINT)
    with pytest.raises(TransitionError) as err:
        transition(request, S.AWAITING_CHECKPOINT, boss, REASON)
    assert err.value.code == "checkpoint_unresolved" and err.value.status_code == 409
    record.resolved_at = timezone.now()
    record.save()
    transition(request, S.AWAITING_CHECKPOINT, boss, REASON)
    assert request.status == S.AWAITING_CHECKPOINT

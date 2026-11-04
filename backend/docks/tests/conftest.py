import pytest
from rest_framework.test import APIClient

from accounts.models import SystemSetting
from accounts.roles import RoleCode as R
from cargo_queue.models import QueueRequest
from cargo_queue.services.state_machine import transition
from cargo_queue.statuses import RequestStatus as S
from cargo_queue.tests.factories import (
    CargoCategoryFactory,
    DockFactory,
    QueueRequestFactory,
    UserFactory,
    make_cargo_ready,
)
from docks.models import CallEvent, Dock, DockCategory
from integrations.sms import get_mock_gateway


@pytest.fixture(autouse=True)
def _mock_sms(settings):
    """Texts go to the in-memory gateway, which starts every test empty and working."""
    settings.SMS_GATEWAY = "mock"
    gateway = get_mock_gateway()
    gateway.sent.clear()
    gateway.fail_times = 0
    yield gateway


@pytest.fixture
def supervisor():
    return UserFactory(role_code=R.SUPERVISOR, username="boss_c")


@pytest.fixture
def dock() -> Dock:
    dock = DockFactory(code="D-01")
    DockCategory.objects.create(dock=dock, category=CargoCategoryFactory(code="GEN"))
    return dock


def client_for(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def set_setting(key: str, value) -> None:
    SystemSetting.objects.update_or_create(key=key, defaults={"value": value})


def assigned(dock: Dock, supervisor, *, cargo_ready: bool = True, **kwargs) -> QueueRequest:
    """A request that has been given `dock` (no automatic call is attempted here)."""
    request = QueueRequestFactory(status=S.AWAITING_DOCK, **kwargs)
    if cargo_ready:
        make_cargo_ready(request)
    transition(request, S.DOCK_ASSIGNED, supervisor, extra={"dock": dock.code})
    return request


def age_call(request: QueueRequest, minutes: int) -> None:
    """Pretend the latest call was made `minutes` ago (no waiting in tests)."""
    import datetime as dt

    from django.utils import timezone

    latest = CallEvent.objects.filter(request=request).order_by("-id").first()
    CallEvent.objects.filter(pk=latest.pk).update(
        called_at=timezone.now() - dt.timedelta(minutes=minutes)
    )


def arrived_request(dock: Dock, supervisor, **kwargs) -> QueueRequest:
    """A customer who was called to `dock` and has arrived (the dock agent is signed in)."""
    from cargo_queue.tests.factories import make_dock_ready
    from docks import calls

    if dock.current_agent_id is None:
        make_dock_ready(dock)
    request = assigned(dock, supervisor, **kwargs)
    assert calls.try_call(request)
    transition(request, S.ARRIVED, dock.current_agent)
    return request


def releasing_request(dock: Dock, supervisor, **kwargs) -> QueueRequest:
    """...and the release has started (the agent counts pieces)."""
    from docks import release

    request = arrived_request(dock, supervisor, **kwargs)
    release.start(request.pk, dock.current_agent)
    request.refresh_from_db()
    return request

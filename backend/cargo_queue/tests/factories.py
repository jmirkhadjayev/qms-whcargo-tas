import datetime as dt
import secrets

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from accounts.models import Role, User
from accounts.roles import RoleCode
from cargo_queue.models import (
    CargoCategory,
    Consignee,
    PermitSource,
    PermitStatus,
    QueueRequest,
    ReleasePermit,
    Shift,
)
from cargo_queue.statuses import RequestStatus
from docks.models import Dock, ReleaseOperation


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ("username",)

    class Params:
        role_code = RoleCode.ADMIN

    username = factory.Sequence(lambda n: f"user{n}")
    full_name = factory.Sequence(lambda n: f"Foydalanuvchi {n}")
    role = factory.LazyAttribute(
        lambda o: Role.objects.get_or_create(code=o.role_code, defaults={"name": o.role_code})[0]
    )

    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        self.set_password(extracted or "pass-12345")
        if create:
            self.save(update_fields=["password"])


class CargoCategoryFactory(DjangoModelFactory):
    class Meta:
        model = CargoCategory
        django_get_or_create = ("code",)

    code = "GEN"
    name = "Umumiy yuk"


class ShiftFactory(DjangoModelFactory):
    class Meta:
        model = Shift

    name = factory.Sequence(lambda n: f"Smena {n}")
    starts_at = dt.time(8, 0)
    ends_at = dt.time(16, 0)


class ConsigneeFactory(DjangoModelFactory):
    class Meta:
        model = Consignee

    name = factory.Sequence(lambda n: f"Yuk oluvchi {n}")
    phone = "+998901234567"


class DockFactory(DjangoModelFactory):
    class Meta:
        model = Dock
        django_get_or_create = ("code",)

    code = factory.Sequence(lambda n: f"D-{n % 90 + 10:02d}")
    name = factory.LazyAttribute(lambda o: f"Dok {o.code}")


class ReleasePermitFactory(DjangoModelFactory):
    class Meta:
        model = ReleasePermit

    awb_number = factory.Sequence(lambda n: f"123-{n:08d}")
    permit_number = factory.Sequence(lambda n: f"P-{n}")
    source = PermitSource.MANUAL
    status = PermitStatus.VERIFIED
    verified_at = factory.LazyFunction(timezone.now)


class QueueRequestFactory(DjangoModelFactory):
    class Meta:
        model = QueueRequest

    queue_date = factory.LazyFunction(lambda: timezone.localdate())
    queue_number = factory.Sequence(lambda n: n + 1)
    permit = factory.SubFactory(ReleasePermitFactory)
    awb_number = factory.SelfAttribute("permit.awb_number")
    consignee = factory.SubFactory(ConsigneeFactory)
    category = factory.SubFactory(CargoCategoryFactory)
    shift = factory.SubFactory(ShiftFactory)
    pieces_total = 10
    weight_kg = 100
    sms_phone = "+998901234567"
    status = RequestStatus.REGISTERED
    qr_token = factory.LazyFunction(lambda: secrets.token_urlsafe(24))
    created_by = factory.SubFactory(UserFactory, role_code=RoleCode.REG_AGENT, username="creator")


def release(request: QueueRequest, pieces: int, dock: Dock | None = None) -> ReleaseOperation:
    """Record `pieces` as released for `request` (goes through the DB sum trigger)."""
    return ReleaseOperation.objects.create(
        request=request,
        dock=dock or DockFactory(code="D-99"),
        agent=UserFactory(role_code=RoleCode.DOCK_AGENT, username="dock_agent_x"),
        pieces_released=pieces,
    )


def make_dock_ready(dock: Dock, agent_username: str = "dock_agent_ready") -> Dock:
    """A dock agent is signed in at the dock (staff readiness, K27)."""
    from django.utils import timezone

    dock.current_agent = UserFactory(role_code=RoleCode.DOCK_AGENT, username=agent_username)
    dock.agent_ready_at = timezone.now()
    dock.save(update_fields=["current_agent", "agent_ready_at"])
    return dock


def make_cargo_ready(request: QueueRequest) -> None:
    from warehouse.models import WarehouseTask, WarehouseTaskStatus

    WarehouseTask.objects.create(request=request, status=WarehouseTaskStatus.READY)


def make_callable(request: QueueRequest, dock_code: str = "D-60") -> Dock:
    """Give the request a dock and make everything needed for a call ready."""
    dock = make_dock_ready(DockFactory(code=dock_code))
    request.dock = dock
    request.save(update_fields=["dock"])
    make_cargo_ready(request)
    return dock

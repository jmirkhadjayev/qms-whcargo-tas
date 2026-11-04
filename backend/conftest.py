import datetime as dt

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from accounts.models import Role, User
from accounts.roles import RoleCode
from cargo_queue.models import CargoCategory, Shift
from cargo_queue.tests.factories import CargoCategoryFactory, UserFactory


def pytest_collection_modifyitems(config, items):
    """Tests marked `postgres` need triggers/locking and are skipped on the SQLite smoke setup."""
    from django.conf import settings

    if "postgresql" in settings.DATABASES["default"]["ENGINE"]:
        return
    skip = pytest.mark.skip(reason="requires PostgreSQL")
    for item in items:
        if "postgres" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _clear_cache():
    # Login throttling state must not leak between tests.
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def roles(db) -> dict[str, Role]:
    return {
        code.value: Role.objects.get_or_create(code=code, defaults={"name": code.label})[0]
        for code in RoleCode
    }


@pytest.fixture
def make_user(roles):
    def _make(role: RoleCode, username: str | None = None, password: str = "pass-12345") -> User:
        return User.objects.create_user(
            username=username or role.value.lower(),
            password=password,
            full_name=f"Test {role.value}",
            role=roles[role.value],
        )

    return _make


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def login_as(api_client, make_user):
    def _login(role: RoleCode) -> APIClient:
        user = make_user(role)
        api_client.force_authenticate(user=user)
        return api_client

    return _login


@pytest.fixture
def shifts(db) -> list[Shift]:
    """Three shifts that together cover the whole day (the last one crosses midnight)."""
    return [
        Shift.objects.create(name="1-smena", starts_at=dt.time(8), ends_at=dt.time(16)),
        Shift.objects.create(name="2-smena", starts_at=dt.time(16), ends_at=dt.time(23, 59, 59)),
        Shift.objects.create(name="3-smena", starts_at=dt.time(23, 59, 59), ends_at=dt.time(8)),
    ]


@pytest.fixture
def category(db) -> CargoCategory:
    return CargoCategoryFactory(code="GEN", name="Umumiy yuk")


@pytest.fixture
def reg_user(db):
    return UserFactory(role_code=RoleCode.REG_AGENT, username="reg_agent")


@pytest.fixture
def reg_client(reg_user) -> APIClient:
    client = APIClient()
    client.force_authenticate(reg_user)
    return client


@pytest.fixture
def payload(category) -> dict:
    """A valid registration body. AWB ending in an even digit passes the mock permit provider."""
    return {
        "awb_number": "176-12345670",
        "consignee_name": "Toshkent Savdo MChJ",
        "consignee_tin": "123456789",
        "representative_name": "Aliyev Vali",
        "sms_phone": "+998 90 123-45-67",
        "pieces_total": 12,
        "weight_kg": "345.50",
        "vehicle_plate": "01 A 123 BC",
        "category": "GEN",
        "notes": "Ehtiyotkorlik bilan",
    }

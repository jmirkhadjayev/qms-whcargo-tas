import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from accounts.models import Role, SystemSetting, User
from accounts.roles import RoleCode
from accounts.settings_store import DEFAULTS, get_setting

pytestmark = pytest.mark.django_db


@override_settings(DEBUG=True)  # the test runner forces DEBUG=False
def test_seed_creates_one_user_per_role_and_is_idempotent(monkeypatch):
    monkeypatch.setenv("SEED_PASSWORD", "demo-pass-123")
    call_command("seed")
    call_command("seed")
    assert Role.objects.count() == len(RoleCode)
    assert User.objects.count() == len(RoleCode)
    assert set(User.objects.values_list("role__code", flat=True)) == {c.value for c in RoleCode}
    assert User.objects.get(username="supervisor").check_password("demo-pass-123")
    assert SystemSetting.objects.count() == len(DEFAULTS)


@override_settings(DEBUG=True)
def test_seed_requires_password(monkeypatch):
    monkeypatch.delenv("SEED_PASSWORD", raising=False)
    with pytest.raises(CommandError):
        call_command("seed")


@override_settings(DEBUG=False)
def test_seed_refuses_outside_debug(monkeypatch):
    monkeypatch.setenv("SEED_PASSWORD", "demo-pass-123")
    with pytest.raises(CommandError):
        call_command("seed")


def test_setting_default_and_override():
    assert get_setting("no_show_timeout_min") == 10
    SystemSetting.objects.create(key="no_show_timeout_min", value=15)
    assert get_setting("no_show_timeout_min") == 15


def test_unknown_setting_raises():
    with pytest.raises(KeyError):
        get_setting("does_not_exist")


def test_create_superuser_gets_admin_role():
    user = User.objects.create_superuser("root", "pass-12345", full_name="Root")
    assert user.role.code == RoleCode.ADMIN
    assert user.is_staff and user.is_superuser

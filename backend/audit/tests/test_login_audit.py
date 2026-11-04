import pytest

from accounts.roles import RoleCode
from audit.models import AuditAction, AuditLog

pytestmark = pytest.mark.django_db


def test_successful_login_is_audited(api_client, make_user):
    user = make_user(RoleCode.SUPERVISOR, username="boss", password="secret-12345")
    api_client.post("/api/auth/login/", {"username": "boss", "password": "secret-12345"})
    entry = AuditLog.objects.get(action=AuditAction.LOGIN)
    assert entry.user == user and entry.entity == "users" and entry.entity_id == user.pk
    assert entry.ip_address == "127.0.0.1"


def test_failed_login_is_audited_without_a_user_and_without_the_password(api_client, make_user):
    make_user(RoleCode.SUPERVISOR, username="boss", password="secret-12345")
    api_client.post("/api/auth/login/", {"username": "boss", "password": "wrong-pass"})
    entry = AuditLog.objects.get(action=AuditAction.LOGIN_FAILED)
    assert entry.user is None
    assert entry.new_value == {"username": "boss"}
    assert "wrong-pass" not in str(entry.new_value)

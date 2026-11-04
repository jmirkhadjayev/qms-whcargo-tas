import pytest
from rest_framework.test import APIClient

from accounts import errors
from accounts.roles import RoleCode

pytestmark = pytest.mark.django_db

LOGIN_URL = "/api/auth/login/"


def test_login_success_returns_user_and_role(api_client, make_user):
    make_user(RoleCode.SUPERVISOR, username="boss", password="secret-12345")
    response = api_client.post(LOGIN_URL, {"username": "boss", "password": "secret-12345"})
    assert response.status_code == 200
    assert response.json()["role"] == "SUPERVISOR"
    assert api_client.get("/api/auth/me/").json()["username"] == "boss"


def test_login_wrong_password_uzbek_message(api_client, make_user):
    make_user(RoleCode.REG_AGENT, username="agent", password="secret-12345")
    response = api_client.post(LOGIN_URL, {"username": "agent", "password": "wrong"})
    assert response.status_code == 400
    assert response.json()["detail"] == errors.INVALID_CREDENTIALS


def test_login_inactive_user_rejected(api_client, make_user):
    user = make_user(RoleCode.REG_AGENT, username="gone", password="secret-12345")
    user.is_active = False
    user.save()
    response = api_client.post(LOGIN_URL, {"username": "gone", "password": "secret-12345"})
    assert response.status_code == 400


def test_login_requires_csrf_token(make_user):
    make_user(RoleCode.REG_AGENT, username="agent", password="secret-12345")
    client = APIClient(enforce_csrf_checks=True)
    response = client.post(LOGIN_URL, {"username": "agent", "password": "secret-12345"})
    assert response.status_code == 403


def test_login_with_csrf_token_succeeds(make_user):
    make_user(RoleCode.REG_AGENT, username="agent", password="secret-12345")
    client = APIClient(enforce_csrf_checks=True)
    token = client.get("/api/auth/csrf/").json()["csrf_token"]
    response = client.post(
        LOGIN_URL,
        {"username": "agent", "password": "secret-12345"},
        HTTP_X_CSRFTOKEN=token,
    )
    assert response.status_code == 200


def test_me_unauthenticated_uzbek_message(api_client):
    response = api_client.get("/api/auth/me/")
    assert response.status_code == 403 or response.status_code == 401
    assert response.json()["detail"] == errors.NOT_AUTHENTICATED


def test_logout_ends_session(api_client, make_user):
    make_user(RoleCode.ADMIN, username="adm", password="secret-12345")
    api_client.post(LOGIN_URL, {"username": "adm", "password": "secret-12345"})
    assert api_client.post("/api/auth/logout/").status_code == 204
    assert api_client.get("/api/auth/me/").status_code in (401, 403)


def test_login_is_throttled(api_client, make_user):
    make_user(RoleCode.REG_AGENT, username="agent", password="secret-12345")
    statuses = [
        api_client.post(LOGIN_URL, {"username": "agent", "password": "bad"}).status_code
        for _ in range(12)
    ]
    assert statuses[-1] == 429

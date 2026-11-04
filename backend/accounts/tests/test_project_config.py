import pytest
from django.conf import settings

pytestmark = pytest.mark.django_db


def test_time_and_language_settings():
    assert settings.TIME_ZONE == "Asia/Tashkent"
    assert settings.USE_TZ is True
    assert settings.LANGUAGE_CODE == "uz"
    assert settings.AUTH_USER_MODEL == "accounts.User"


def test_health_endpoint(client):
    response = client.get("/api/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_schema_and_docs(client):
    schema = client.get("/api/schema/")
    assert schema.status_code == 200
    assert b"/api/auth/login/" in schema.content
    assert client.get("/api/docs/").status_code == 200

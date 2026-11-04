"""Every endpoint x every role: allowed roles get through, all others are refused (403)."""

import pytest
from rest_framework.test import APIClient

from accounts.roles import RoleCode as R
from cargo_queue.statuses import RequestStatus as S
from cargo_queue.tests.factories import QueueRequestFactory, UserFactory
from warehouse.services import create_task_for

pytestmark = [pytest.mark.django_db, pytest.mark.postgres]

ALL = set(R)
OPERATIONAL = {R.REG_AGENT, R.WAREHOUSE, R.DOCK_AGENT, R.SUPERVISOR, R.CHECKPOINT, R.ADMIN}

# (method, path template, allowed roles). Written out independently of the view code.
ENDPOINTS = [
    ("GET", "/api/requests/", OPERATIONAL),
    ("POST", "/api/requests/", {R.REG_AGENT}),
    ("GET", "/api/requests/{id}/", OPERATIONAL),
    (
        "POST",
        "/api/requests/{id}/transition/",
        {R.WAREHOUSE, R.DOCK_AGENT, R.SUPERVISOR, R.CHECKPOINT, R.ADMIN},
    ),
    ("GET", "/api/requests/{id}/ticket/", {R.REG_AGENT, R.SUPERVISOR}),
    ("POST", "/api/requests/{id}/ticket/reprint/", {R.REG_AGENT, R.SUPERVISOR}),
    ("POST", "/api/permits/check/", {R.REG_AGENT, R.SUPERVISOR}),
    ("POST", "/api/permits/manual-verify/", {R.SUPERVISOR, R.ADMIN}),
    ("POST", "/api/requests/{id}/assign-dock/", {R.SUPERVISOR}),
    ("POST", "/api/requests/{id}/priority/", {R.SUPERVISOR}),
    ("GET", "/api/warehouse/tasks/", {R.WAREHOUSE, R.SUPERVISOR}),
    ("GET", "/api/warehouse/tasks/scan/", {R.WAREHOUSE, R.SUPERVISOR}),
    ("POST", "/api/warehouse/tasks/{task}/start/", {R.WAREHOUSE}),
    ("POST", "/api/warehouse/tasks/{task}/ready/", {R.WAREHOUSE}),
    ("POST", "/api/warehouse/tasks/{task}/problem/", {R.WAREHOUSE}),
    ("POST", "/api/warehouse/tasks/{task}/handover/", {R.WAREHOUSE}),
    ("GET", "/api/dispatcher/overview/", {R.SUPERVISOR, R.ADMIN}),
    ("GET", "/api/dispatcher/queue/", {R.SUPERVISOR, R.ADMIN}),
    ("POST", "/api/dispatcher/docks/D-01/maintenance/", {R.SUPERVISOR}),
    ("POST", "/api/requests/{id}/call/", {R.SUPERVISOR}),
    ("POST", "/api/requests/{id}/recall/", {R.DOCK_AGENT, R.SUPERVISOR}),
    ("POST", "/api/requests/{id}/arrive/", {R.DOCK_AGENT}),
    ("GET", "/api/dock/me/", {R.DOCK_AGENT}),
    ("POST", "/api/dock/checkin/", {R.DOCK_AGENT}),
    ("POST", "/api/dock/checkout/", {R.DOCK_AGENT}),
    ("GET", "/api/dock/scan/", {R.DOCK_AGENT}),
    ("POST", "/api/requests/{id}/resume/", {R.SUPERVISOR}),
    ("POST", "/api/requests/{id}/release/start/", {R.DOCK_AGENT}),
    ("POST", "/api/requests/{id}/release/progress/", {R.DOCK_AGENT}),
    ("POST", "/api/requests/{id}/release/finish/", {R.DOCK_AGENT}),
    ("POST", "/api/requests/{id}/release/partial/", {R.DOCK_AGENT}),
    ("POST", "/api/requests/{id}/problems/", {R.DOCK_AGENT, R.SUPERVISOR}),
    ("GET", "/api/exceptions/", {R.SUPERVISOR, R.ADMIN}),
    ("POST", "/api/exceptions/{id}/resolve/", {R.SUPERVISOR}),
    ("GET", "/api/checkpoint/overview/", {R.CHECKPOINT}),
    ("GET", "/api/checkpoint/scan/", {R.CHECKPOINT}),
    ("POST", "/api/checkpoint/{id}/confirm/", {R.CHECKPOINT}),
    ("POST", "/api/checkpoint/{id}/hold/", {R.CHECKPOINT}),
    ("GET", "/api/lookups/", ALL),
    ("GET", "/api/auth/me/", ALL),
]


def call(client: APIClient, method: str, path: str):
    if method == "GET":
        return client.get(path)
    return client.post(path, {}, format="json")


@pytest.mark.parametrize("role", list(R))
@pytest.mark.parametrize(("method", "path", "allowed"), ENDPOINTS)
def test_role_matrix(role, method, path, allowed):
    task = create_task_for(QueueRequestFactory(status=S.REGISTERED))
    client = APIClient()
    client.force_authenticate(UserFactory(role_code=role, username=f"matrix_{role.value}"))
    response = call(client, method, path.format(id=task.request_id, task=task.pk))
    if role in allowed:
        assert response.status_code != 403, (role, method, path, response.content)
    else:
        assert response.status_code == 403, (role, method, path)
        assert response.json()["detail"] == "Bu amal uchun ruxsatingiz yo‘q."


@pytest.mark.parametrize(("method", "path", "allowed"), ENDPOINTS)
def test_anonymous_is_refused(method, path, allowed):
    request = QueueRequestFactory()
    response = call(APIClient(), method, path.format(id=request.pk, task=1))
    assert response.status_code in (401, 403)
    assert response.json()["detail"] == "Tizimga kiring."


def test_deactivated_user_is_refused():
    user = UserFactory(role_code=R.REG_AGENT, username="gone")
    user.is_active = False
    user.save()
    client = APIClient()
    client.force_authenticate(user)
    assert client.get("/api/requests/").status_code == 403

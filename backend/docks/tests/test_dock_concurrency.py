"""Two supervisors choosing the same dock at the same moment: exactly one wins."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import connection
from rest_framework.test import APIClient

from accounts.roles import RoleCode as R
from cargo_queue.statuses import RequestStatus as S
from cargo_queue.tests.factories import (
    CargoCategoryFactory,
    DockFactory,
    QueueRequestFactory,
    UserFactory,
)
from docks.models import DockCategory, DockState

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.postgres]


def test_two_supervisors_cannot_take_the_same_dock():
    dock = DockFactory(code="D-01")
    DockCategory.objects.create(dock=dock, category=CargoCategoryFactory(code="GEN"))
    first = QueueRequestFactory(status=S.AWAITING_DOCK)
    second = QueueRequestFactory(status=S.AWAITING_DOCK)
    supervisor = UserFactory(role_code=R.SUPERVISOR, username="boss_x")

    def assign(request_id: int) -> int:
        try:
            client = APIClient()
            client.force_authenticate(supervisor)
            response = client.post(
                f"/api/requests/{request_id}/assign-dock/", {"dock": "D-01"}, format="json"
            )
            return response.status_code
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(assign, [first.pk, second.pk]))

    assert sorted(results) == [200, 409]
    dock.refresh_from_db()
    assert dock.state == DockState.BUSY

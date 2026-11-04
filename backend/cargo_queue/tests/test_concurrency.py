"""Real parallelism against PostgreSQL: unique numbers and the release-sum limit."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import IntegrityError, connection

from cargo_queue.models import QueueRequest
from cargo_queue.services.registration import RegistrationData, register_request
from cargo_queue.tests.factories import QueueRequestFactory, release

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.postgres]


def test_parallel_registrations_get_unique_consecutive_numbers(shifts, category, reg_user):
    count = 24

    def worker(index: int) -> int:
        try:
            data = RegistrationData(
                awb_number=f"176-{index * 2:08d}",  # even last digit: the mock permit passes
                consignee_name=f"MChJ {index}",
                sms_phone="+998901234567",
                pieces_total=3,
                weight_kg=5,
                category=category,
            )
            return register_request(data, reg_user).queue_number
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=8) as pool:
        numbers = list(pool.map(worker, range(count)))

    assert sorted(numbers) == list(range(1, count + 1))
    assert QueueRequest.objects.count() == count


def test_parallel_releases_cannot_exceed_the_total():
    request = QueueRequestFactory(pieces_total=10)
    pk = request.pk

    def worker(_: int) -> bool:
        try:
            release(QueueRequest.objects.get(pk=pk), 6)
            return True
        except IntegrityError:
            return False
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, range(2)))

    assert sorted(results) == [False, True]

from celery import shared_task

from docks import calls


@shared_task(name="docks.process_no_shows")
def process_no_shows() -> dict[str, int]:
    """Beat job: recall / requeue / cancel calls that nobody answered in time."""
    return dict(calls.process_no_shows())


@shared_task(name="docks.call_waiting_requests")
def call_waiting_requests() -> int:
    """Beat job: call customers whose dock, cargo and staff have become ready."""
    return calls.call_waiting_requests()

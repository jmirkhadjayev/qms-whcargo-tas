import time

from django.core.management.base import BaseCommand

from docks import calls
from notifications import services as sms


class Command(BaseCommand):
    help = (
        "Run the periodic jobs (no-show timer, waiting calls, pending SMS) in a loop. "
        "For local development without Celery beat; production uses `celery beat`."
    )

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=15, help="seconds between runs")
        parser.add_argument("--once", action="store_true", help="run a single pass and exit")

    def handle(self, *args, **options):
        while True:
            outcome = calls.process_no_shows()
            called = calls.call_waiting_requests()
            texts = sms.send_pending(older_than_seconds=0)
            if outcome or called or texts:
                self.stdout.write(f"no-shows={dict(outcome)} called={called} sms={texts}")
            if options["once"]:
                return
            time.sleep(options["interval"])

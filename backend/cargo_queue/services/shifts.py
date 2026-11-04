import datetime as dt

from django.utils import timezone

from cargo_queue.models import Shift


def shift_covers(shift: Shift, at: dt.time) -> bool:
    """True if `at` falls inside the shift; handles shifts that cross midnight (decision K24)."""
    if shift.starts_at <= shift.ends_at:
        return shift.starts_at <= at < shift.ends_at
    return at >= shift.starts_at or at < shift.ends_at


def shift_for(moment: dt.datetime) -> Shift | None:
    """The shift active at `moment` (interpreted in the project time zone, Asia/Tashkent)."""
    local_time = timezone.localtime(moment).time()
    for shift in Shift.objects.all():
        if shift_covers(shift, local_time):
            return shift
    return None

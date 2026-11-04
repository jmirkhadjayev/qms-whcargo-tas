from __future__ import annotations

from functools import partial

from django.db import transaction

from audit import services as audit
from audit.models import AuditAction
from cargo_queue import errors, events
from cargo_queue.models import QueueRequest
from cargo_queue.statuses import INACTIVE_STATUSES
from config.errors import DomainError


def set_priority(request_id: int, priority: int, user, reason: str = "") -> QueueRequest:
    """Change the queue priority. It only affects ordering; it never skips a permit or a
    safety procedure (TZ 5.3). The change is audited."""
    with transaction.atomic():
        queue_request = QueueRequest.objects.select_for_update().get(pk=request_id)
        if queue_request.status in INACTIVE_STATUSES:
            raise DomainError("priority_final", errors.PRIORITY_FINAL, 409)
        old = queue_request.priority
        if old != priority:
            queue_request.priority = priority
            queue_request.save(update_fields=["priority"])
            audit.log(
                AuditAction.UPDATE,
                "queue_requests",
                queue_request.pk,
                user=user,
                old_value={"priority": old},
                new_value={"priority": priority, "reason": reason.strip()},
            )
            transaction.on_commit(
                partial(events.publish_request_changed, queue_request.pk, "priority")
            )
    return queue_request

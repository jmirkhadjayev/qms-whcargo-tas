from django.db import models


class RequestStatus(models.TextChoices):
    REGISTERED = "REGISTERED", "Ro‘yxatdan o‘tkazildi"
    AWAITING_PREP = "AWAITING_PREP", "Tayyorlashni kutmoqda"
    PREP_STARTED = "PREP_STARTED", "Tayyorlash boshlandi"
    CARGO_READY = "CARGO_READY", "Yuk tayyorlandi"
    AWAITING_DOCK = "AWAITING_DOCK", "Dok belgilanishini kutmoqda"
    DOCK_ASSIGNED = "DOCK_ASSIGNED", "Dok belgilandi"
    CALLED = "CALLED", "Mijoz chaqirildi"
    ARRIVED = "ARRIVED", "Mijoz yetib keldi"
    RELEASE_STARTED = "RELEASE_STARTED", "Yuk berish boshlandi"
    RELEASED = "RELEASED", "Yuk berish yakunlandi"
    PARTIALLY_RELEASED = "PARTIALLY_RELEASED", "Qisman berildi"
    AWAITING_CHECKPOINT = "AWAITING_CHECKPOINT", "NO‘Pda tasdiqlashni kutmoqda"
    EXIT_CONFIRMED = "EXIT_CONFIRMED", "Chiqib ketish tasdiqlandi"
    SUSPENDED = "SUSPENDED", "To‘xtatib turildi"
    CANCELLED = "CANCELLED", "Bekor qilindi"
    CLOSED = "CLOSED", "Yopildi"


S = RequestStatus

# A request in these states no longer occupies its AWB / permit (partial unique indexes).
INACTIVE_STATUSES = [S.CANCELLED, S.CLOSED]

# States before RELEASE_STARTED: a SUPERVISOR may cancel from here (CLAUDE.md "Qo‘shimcha").
PRE_RELEASE_STATUSES = [
    S.REGISTERED,
    S.AWAITING_PREP,
    S.PREP_STARTED,
    S.CARGO_READY,
    S.AWAITING_DOCK,
    S.DOCK_ASSIGNED,
    S.CALLED,
    S.ARRIVED,
]

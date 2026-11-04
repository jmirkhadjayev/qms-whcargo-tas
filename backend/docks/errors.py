"""User-facing messages for docks (Uzbek, Latin script)."""

DOCK_REQUIRED = "Dokni ko‘rsating."
DOCK_UNKNOWN = "Dok topilmadi yoki faol emas."
DOCK_MAINTENANCE = "Dok ta’mirda — uni belgilab bo‘lmaydi."
DOCK_BUSY = "Dok band — boshqa ariza xizmat ko‘rsatilmoqda."
DOCK_BUSY_NO_MAINTENANCE = "Dok band — uni ta’mirga qo‘yib bo‘lmaydi."
DOCK_CATEGORY_MISMATCH = "Bu dok ushbu toifadagi yuk bilan ishlay olmaydi."

# Calling (TZ 3.3 / 3.4)
CALL_BLOCKERS = {
    "no_dock": "Dok belgilanmagan.",
    "cargo_not_ready": "Yuk hali tayyor emas.",
    "dock_unavailable": "Dok xizmatga yaroqsiz (ta’mirda yoki faol emas).",
    "agent_not_ready": "Dok xodimi tayyor emas (dokda ro‘yxatdan o‘tmagan).",
}
CALL_NOT_READY = "Mijozni chaqirib bo‘lmaydi: "
RECALL_LIMIT = "Takroriy chaqiruvlar limiti tugagan."
NOT_YOUR_DOCK = "Bu ariza sizning dokingizga tegishli emas."
AGENT_NOT_AT_DOCK = "Avval dokda ro‘yxatdan o‘ting."
DOCK_HAS_AGENT = "Bu dokda boshqa xodim ishlayapti."
CHECKOUT_BLOCKED = "Dokda mijoz bor — dokdan chiqib bo‘lmaydi."
DOCK_NOT_AVAILABLE = "Dok ta’mirda yoki faol emas."
SCAN_NOT_FOUND = "Bu talon sizning dokingiz uchun topilmadi."
SCAN_EMPTY = "Kod kiritilmagan."

# Release (TZ 5.2)
RELEASE_NOT_STARTED = "Yuk berish hali boshlanmagan."
RELEASE_EXCEEDS = "Berilgan o‘rinlar soni jami o‘rinlardan oshib ketdi."
PARTIAL_REASON_REQUIRED = "Qisman berish sababi va izohi majburiy."
NOT_AT_DOCK = "Bu ariza hozir dokda emas."
PARTIAL_REASONS = {
    "MISSING": "Yuk topilmadi",
    "DAMAGE": "Yuk shikastlangan",
    "SHORTAGE": "Kamomad",
    "CUSTOMER": "Mijoz qolganini olmadi",
    "OTHER": "Boshqa sabab",
}

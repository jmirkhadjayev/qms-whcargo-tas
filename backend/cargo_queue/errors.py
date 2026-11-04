"""User-facing messages for the queue domain (Uzbek, Latin script)."""

# Permits (TZ 3.1)
AWB_INVALID = "AWB raqami noto‘g‘ri formatda (masalan: 123-45678901)."
PERMIT_NOT_FOUND = "Chiqarishga ruxsatnoma topilmadi yoki tasdiqlanmagan."
PERMIT_NOT_VERIFIED = "Chiqarishga ruxsatnoma tasdiqlanmagan."
PERMIT_REVOKED = "Chiqarishga ruxsatnoma bekor qilingan."
PERMIT_EXPIRED = "Chiqarishga ruxsatnoma muddati tugagan."
PERMIT_AWB_MISMATCH = "Ruxsatnoma boshqa AWB uchun berilgan."
PERMIT_MANUAL_REQUIRED = "Ruxsatnoma topilmadi. Smena boshlig‘i uni qo‘lda tasdiqlashi kerak."

# Registration
DUPLICATE_ACTIVE_REQUEST = "Bu AWB bo‘yicha faol ariza allaqachon mavjud."
CATEGORY_UNKNOWN = "Yuk toifasi topilmadi."
NO_SHIFT = "Joriy vaqt uchun smena aniqlanmadi. Administratorga murojaat qiling."
PHONE_INVALID = "Telefon raqami +998XXXXXXXXX ko‘rinishida bo‘lishi kerak."
PLATE_INVALID = "Davlat raqami noto‘g‘ri formatda."

# State machine
INVALID_TRANSITION = "Bu holatdan tanlangan holatga o‘tish mumkin emas."
ROLE_FORBIDDEN = "Bu o‘tishni bajarishga ruxsatingiz yo‘q."
REASON_REQUIRED = "Sabab ko‘rsatilishi shart."
OPEN_EXCEPTIONS = "Hal qilinmagan istisno bor — arizani yopib bo‘lmaydi."
RELEASE_INCOMPLETE = "Barcha o‘rinlar berilmagan — to‘liq berildi deb belgilab bo‘lmaydi."
RELEASE_NOT_PARTIAL = "Hamma o‘rinlar berilgan — qisman berish emas."
NO_REMAINDER = "Qolgan o‘rinlar yo‘q — qayta tayyorlashga o‘tkazib bo‘lmaydi."
CLOSE_WITH_REMAINDER = (
    "Qolgan o‘rinlar bor: yopishni faqat smena boshlig‘i hujjatlashtirilgan sabab bilan bajaradi."
)
RESUME_WRONG_TARGET = "To‘xtatib turilgan ariza faqat oldingi holatiga qaytariladi."
CANCEL_AFTER_RELEASE = "Yuk berish boshlangandan keyin arizani bekor qilib bo‘lmaydi."

CHECKPOINT_UNRESOLVED = "NO‘P tafovuti hal qilinmagan — avval istisnoni hal qiling."

NOT_SUSPENDED = "Ariza to‘xtatib turilmagan."

# Priority
PRIORITY_FINAL = "Yakunlangan arizaning ustuvorligini o‘zgartirib bo‘lmaydi."

# Lookups / lists
REQUEST_NOT_FOUND = "Ariza topilmadi."
FILTER_DATE_INVALID = "Sana YYYY-MM-DD ko‘rinishida bo‘lishi kerak."

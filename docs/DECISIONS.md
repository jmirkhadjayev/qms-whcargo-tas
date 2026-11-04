# Qarorlar jurnali

TZ da aniq bo‘lmagan masalalar bo‘yicha qabul qilingan qarorlar. Format: sana — qaror — sabab.

Belgi: **[vaqtinchalik]** — buyurtmachi tasdig‘ini kutadigan qiymat/qoida.

## 2026-11-04 — reja tasdiqlanishi (TZ / ER / CLAUDE.md ziddiyatlari)

### Hujjatlar o‘rtasidagi ziddiyatlar

- **K1 Rollar.** 7 rol: `REG_AGENT, WAREHOUSE, DOCK_AGENT, SUPERVISOR, CHECKPOINT, MANAGER, ADMIN`. ER'dagi ro‘yxatda `MANAGER` yetishmasdi.
- **K2 Istisno modeli.** Model `ExceptionRecord`, `db_table="exceptions"`, app `exceptions_app`.
- **K3 Istisno turlari.** ER'dagi 7 tur asos: `MISSING, DAMAGE, SHORTAGE, MISMATCH, PARTIAL, NO_SHOW, CHECKPOINT`. CLAUDE.md'dagi atamalar: kamomad=SHORTAGE, shikast=DAMAGE, tafovut=MISMATCH/CHECKPOINT, kelmaslik=NO_SHOW.
- **K4 User maydonlari.** Django standart nomlari: `password` (ER'da `password_hash`), `last_login` (ER'da `last_login_at`). Sabab: `AbstractBaseUser` bilan mos, `check_password`/`login` ishlaydi.
- **K5 Ruxsatnoma manbasi.** `release_permits.source` ga `MOCK` qo‘shildi. Prod sozlamasi mock provayder bilan ishga tushishni rad etadi.
- **K6 Audit.** `audit_log.user_id` va `entity_id` — nullable (rad etilgan urinish, tizim harakati, muvaffaqiyatsiz login). Yangi `action` qiymatlari: `TRANSITION, PERMIT_REJECTED, LOGIN_FAILED, REOPEN, PRINT, REPRINT`.
- **K7 Navbat raqami.** Yangi jadval `queue_counters(queue_date PK, last_number)`. Raqam `INSERT … ON CONFLICT DO UPDATE … RETURNING` bilan, ariza yaratilayotgan tranzaksiyada olinadi.
- **K8 Navbat tartibi.** `queue_requests.sort_at` qo‘shildi. Tartib: `(priority DESC, sort_at ASC)`. "Navbat oxiriga o‘tkazish" — `sort_at = now()`. `queue_number` o‘zgarmaydi (talonda bosilgan).
- **K9 Tarixni himoyalash.** 1-bosqichda: trigger + testlar. DB darajasidagi huquqlar (ikki rol: migratsiya egasi va faqat INSERT/SELECT huquqli ilova roli) — 5-bosqichda prod compose bilan birga.
- **K10 Qisman berish cheklovi.** Qatorda `CHECK (pieces_released >= 0)`; yig‘indi (`sum ≤ pieces_total`) uchun constraint trigger + service tekshiruvi.

### Holatlar mashinasi

- **K11 Qayta ochish.** `CLOSED → EXIT_CONFIRMED` (faqat ADMIN, sabab majburiy). `closed_at` tozalanadi, tarix saqlanadi.
- **K12 SUSPENDED'dan qaytish.** Oxirgi SUSPENDED'ga o‘tishning `from_status` qiymatiga, faqat SUPERVISOR. SUSPENDED'ni qayta SUSPENDED qilib bo‘lmaydi.
- **K13 To‘xtatish va bekor qilish.** NO‘P faqat `AWAITING_CHECKPOINT` dan to‘xtata oladi. SUPERVISOR `CLOSED`, `CANCELLED`, `SUSPENDED` dan boshqa hamma holatdan to‘xtata oladi. `SUSPENDED → CANCELLED` faqat u `RELEASE_STARTED` dan oldingi holatdan kirgan bo‘lsa.
- **K14 Qisman berishdan keyingi oqim.** Qabul qilindi: bir xil ariza va navbat raqami; `EXIT_CONFIRMED → AWAITING_PREP` (`sort_at = now()`), qoldiq = `pieces_total − sum(released)`, qoldiq uchun yangi `WarehouseTask`. Qoldiqsiz yopish: `EXIT_CONFIRMED → CLOSED` (SUPERVISOR, hujjatlashtirilgan sabab bilan, TZ 5.2).
- **K15 Oraliq holatlar.** `RELEASED` / `PARTIALLY_RELEASED` → `AWAITING_CHECKPOINT` bitta tranzaksiyada (tarixda 2 qator). `RELEASED` faqat `sum(released) == pieces_total` bo‘lsa.
- **K16 "Muammo" tugmasi.** Ombor yoki dok agenti "Muammo" bossa `ExceptionRecord` yaratiladi va smena boshlig‘iga xabar boradi. Ariza holatini faqat SUPERVISOR o‘zgartiradi.
- **K17 Yopishni to‘suvchi istisnolar.** `NO_SHOW` — mijoz kelganda tizim tomonidan avtomatik hal qilinadi. `PARTIAL` — qoldiq berilganda yoki hujjatlashtirilgan qaror bilan hal qilinadi.

### Ruxsatnoma, ariza, rollar

- **K18 Qo‘lda tasdiqlash.** Faqat SUPERVISOR/ADMIN (`POST /api/permits/manual-verify`). Agent `check` orqali natijani ko‘radi. DB trigger: `status = VERIFIED`, `valid_until` o‘tmagan, `permit.awb_number == request.awb_number`.
- **K19 Takroriy ariza.** Faol (`CANCELLED`/`CLOSED` emas) arizalar uchun `awb_number` va `permit_id` bo‘yicha qisman UNIQUE indeks. Bekor qilingandan keyin ruxsatnoma amal qilsa, qayta ro‘yxatga olish mumkin.
- **K20 Rad etish auditi.** Tekshiruv va `PERMIT_REJECTED` audit yozuvi xato ko‘tarilishidan oldin, alohida tranzaksiyada (rollback yozuvni yo‘qotmasligi uchun).
- **K21 AWB formati.** `^\d{3}-?\d{8}$` (normallashtirilgan: `NNN-NNNNNNNN`). Mock: oxirgi raqam juft — tasdiqlangan, toq — rad; raqam bo‘lmasa — "AWB formati noto‘g‘ri".
- **K22 Vakil.** `queue_requests.representative_name` qo‘shildi. `consignees` — ma’lumotnoma, `tin` nullable (jismoniy shaxs), bo‘lsa takrorlanmaydi.
- **K23 ADMIN.** Administratsiya, hammasini o‘qish va `CLOSED` ni qayta ochish. Operatsion ishlarni (ro‘yxatga olish, dok, ombor, NO‘P) qilmaydi.
- **K24 Sana va smena.** `queue_date` = Asia/Tashkent taqvim kuni. `shift_id` ro‘yxatga olish vaqti bo‘yicha belgilanadi; kechani kesib o‘tuvchi smena (`ends_at < starts_at`) qo‘llab-quvvatlanadi. Hisobotlar ro‘yxatga olish smenasi bo‘yicha.
- **K25 Autentifikatsiya.** **Session (cookie + CSRF)**, JWT emas. Sabab: Channels `AuthMiddlewareStack` WebSocket'ni ham qoplaydi; foydalanuvchi o‘chirilsa darhol kuchini yo‘qotadi (TZ 10); Vite proxy orqali bir origin.
- **K26 Xato xabarlari.** Foydalanuvchiga ko‘rinadigan xabarlar o‘zbekcha, o‘z lug‘atidan (`accounts/errors.py`), DRF standart xabarlari `config/exception_handler.py` orqali almashtiriladi.

### Keyingi bosqichlar uchun sxemaga ta’sir qiluvchilar

- **K27 Xodim tayyorligi.** `docks.current_agent_id` (nullable FK) va `docks.agent_ready_at` qo‘shiladi.
- **K28 Kelmaslik reglamenti [vaqtinchalik].** `SystemSetting` standartlari: `no_show_timeout_min=10`, `max_recalls=2`, `no_show_action="REQUEUE"`, `max_requeues=1` (undan keyin `CANCELLED`). Buyurtmachi tasdiqlashi shart (TZ 5.1).
- **K29 Dok holati.** `docks.state` — saqlanadigan maydon; holatlar mashinasining yon ta’siri sifatida yangilanadi (2–3-bosqich).

## 2026-11-04 — 0-bosqich qarorlari

- **Loyiha ildizi** — `yuk-navbat/`. Git hali `init` qilinmagan, commit yo‘q (foydalanuvchi so‘ramaguncha).
- **Seed:** 0-bosqichda faqat rollar, foydalanuvchilar va `SystemSetting` standartlari. Dok/toifa/smena seed'i 1-bosqichda, modellar paydo bo‘lgach qo‘shiladi.
- **`config/settings/test.py`** qo‘shildi (base/dev/prod dan tashqari): tez parol xeshlash va xotiradagi channel layer, testlar uchun.
- **Lokal tutun-tekshiruv:** Docker bo‘lmagan mashinada `USE_SQLITE=1` (faqat `dev`/`test` sozlamalarida). PostgreSQL trigger'lari kiritilgan 1-bosqichdan boshlab testlar PostgreSQL talab qiladi; CI va compose'da faqat PostgreSQL.
- **Yangi kutubxonalar (sabab bilan):**
  - backend: `psycopg[binary]` (PostgreSQL drayveri), `daphne` (ASGI server), `channels-redis` (Channels layer), `django-stubs` (mypy plagini).
  - frontend: `openapi-typescript` + `openapi-fetch` (CLAUDE.md talabi: klient OpenAPI sxemasidan), `@fontsource/ibm-plex-*` (LAN'da shrift internetsiz ishlashi uchun o‘zida saqlanadi).
- **Login urinishlari** DRF throttle (`login` scope, 10/daqiqa) bilan cheklangan. Audit'ga yozish `audit` app 1-bosqichda paydo bo‘lgach ulanadi.

## 2026-11-04 — 1-bosqich qarorlari

- **Sxema:** ER'dagi barcha jadvallar va migratsiyalar 1-bosqichda qurildi. `dock_categories` — oddiy `id` + `UNIQUE(dock, category)` (Django 5.2 FK/admin bilan qulay; ER'dagi "composite PK" o‘rniga).
- **DB trigger'lar** (faqat PostgreSQL, migratsiyalarda): `audit_log` va `request_status_history` — UPDATE/DELETE taqiqi (`APPEND_ONLY`); `queue_requests` — DELETE taqiqi va INSERT'da ruxsatnoma tekshiruvi (`PERMIT_MISSING | PERMIT_NOT_VERIFIED | PERMIT_EXPIRED | PERMIT_AWB_MISMATCH`); `release_operations` — yig‘indi cheklovi (`RELEASE_EXCEEDS_TOTAL`), bunda ariza qatori `FOR UPDATE` bilan bloklanadi, shuning uchun parallel berishlar ketma-ket bajariladi. TRUNCATE taqiqlanmagan (test tozalash uchun); ish bazasida huquqlar bilan cheklash 5-bosqichda (K9).
- **`status` himoyasi:** `QueueRequest.save()` / `QuerySet.update(status=…)` / `bulk_update` holatni o‘zgartirishga ruxsat bermaydi; faqat `state_machine.transition` vaqtincha bayroq qo‘yadi. Testlar bayroq boshqa joyda ishlatilmasligini tekshiradi. Arizani `delete()` qilish ham taqiqlangan.
- **Holatlar mashinasi:** deklarativ jadval (`TRANSITIONS`), guard va yon ta’sirlar (`sort_at`, `dock`, `closed_at`). `CALLED → CANCELLED` ni `DOCK_AGENT` va tizim bajaradi (kelmaslik reglamenti, sabab majburiy); `SUPERVISOR` RELEASE_STARTED'dan oldingi har qanday holatdan (ikkinchi sikl — `AWAITING_PREP` ham) bekor qila oladi. Chaqiruv tayyorligi guard'i (yuk/dok/xodim) 3-bosqichda `register_guard` orqali ulanadi.
- **O‘tish endpointi** (`POST /api/requests/{id}/transition/`) rollari: WAREHOUSE, DOCK_AGENT, SUPERVISOR, CHECKPOINT, ADMIN. `REG_AGENT` va `MANAGER` o‘tish qila olmaydi. Aniq huquq jadvalda (rol + tizim), endpoint faqat umumiy eshik.
- **Ruxsatnoma endpointlari:** `permits/check` — REG_AGENT, SUPERVISOR (ADMIN operatsion ish qilmaydi, K23); `permits/manual-verify` — SUPERVISOR, ADMIN. Mock provayder faqat tasdiqlangan AWB uchun `ReleasePermit` (`source=MOCK`) yaratadi; rad etilganlar faqat auditga yoziladi.
- **Rad etish auditi:** har bir rad etilgan tekshiruv/ro‘yxatga olish urinishi `PERMIT_REJECTED` sifatida alohida tranzaksiyada yoziladi (K20). Login (`LOGIN`, `LOGIN_FAILED`) auditi ham ulandi (0-bosqichdagi rejaga muvofiq); parol hech qachon yozilmaydi.
- **Talon:** QR faqat `qr_token` ni saqlaydi (shaxsga doir ma’lumotsiz). Ro‘yxatga olishda birinchi `Ticket` yaratiladi; qayta chop etish `is_reprint=true` + `REPRINT` audit. Chop etish sahifasi: `/print/ticket/:id` (80 mm, `@page size: 80mm auto`), rollar: REG_AGENT, SUPERVISOR.
- **Ro‘yxatga olish validatsiyasi:** telefon `+998XXXXXXXXX` (bo‘shliq/chiziqcha olib tashlanadi), davlat raqami `[A-Z0-9]{5,10}` (katta harfga o‘tkaziladi), AWB `NNN-NNNNNNNN`. Smena aniqlanmasa (sozlanmagan) ro‘yxatga olish `409 no_shift` bilan to‘xtaydi.
- **Ro‘yxat API:** sahifalash (50, `page_size` ≤ 200); filtrlar `date`, `status` (vergul bilan), `dock`, `category`, `shift`, `q` (AWB bo‘lagi yoki navbat raqami).
- **WebSocket:** 1-bosqichda faqat `dispatcher` guruhiga `request.status` hodisasi (`on_commit`); broker ishlamasa so‘rov buzilmaydi (xato logga yoziladi). Guruhlar `warehouse`, `dock.<code>` 2-bosqichda.
- **Test muhiti:** DB trigger testlari `@pytest.mark.postgres`; SQLite smoke rejimida o‘tkazib yuboriladi. Bu mashinada Docker yo‘q edi, shuning uchun testlar vaqtincha o‘rnatilgan PostgreSQL 16.2 (`pgserver`, loyiha bog‘liqligi emas) ustida o‘tkazildi; CI va compose haqiqiy `postgres:16` ishlatadi.

## 2026-11-04 — 2-bosqich qarorlari

- **Ombor topshirig‘i** ro‘yxatga olish bilan bir tranzaksiyada yaratiladi; tizim arizani `REGISTERED → AWAITING_PREP` ga o‘tkazadi (ro‘yxatga olish javobida holat endi `AWAITING_PREP`, tarixda 2 qator).
- **Ombor oqimi:** `start` (NEW→IN_PROGRESS, ariza `PREP_STARTED`, ixtiyoriy joylashuv), `ready` (READY; ariza `CARGO_READY` — xodim, so‘ng `AWAITING_DOCK` — tizim), `problem`, `handover` (READY→HANDED_OVER, faqat dok belgilangan bo‘lsa). `storage_location` tashqi tizimdan kelmaydi (AWERY noma’lum) — xodim `start` paytida kiritadi.
- **Muammo (K16):** `problem` turlari MISSING/DAMAGE/SHORTAGE/MISMATCH; `ExceptionRecord` yaratiladi, topshiriq `PROBLEM` bo‘ladi, ariza holati o‘zgarmaydi. `PROBLEM` dan ombor xodimi davom ettira olmaydi; hal qilish va davom ettirish 4-bosqichda (smena boshlig‘i). To‘xtatib turilgan (`SUSPENDED`) arizada `start`/`ready` `409 request_suspended` qaytaradi.
- **Skanerlash:** USB skaner klaviatura kiritishi sifatida ishlaydi (kod maydoni + Enter); kod = talon QR tokeni, AWB (tirelari bilan yoki tiresiz) yoki navbat raqami. Kamera orqali skanerlash keyinga qoldirildi (brauzer `BarcodeDetector` qo‘llab-quvvatlashiga bog‘liq; qurilma tanlangach qo‘shiladi).
- **Dok belgilash:** `POST /api/requests/{id}/assign-dock/` (faqat SUPERVISOR). Tekshiruvlar: dok mavjud va faol, ta’mirda emas, band emas, toifaga mos (`DockCategory`, TZ 5.3); dok qatori bloklanadi, shuning uchun ikki smena boshlig‘i bir dokni ola olmaydi. Umumiy `transition` endpointi `DOCK_ASSIGNED` ga dokni ko‘rsatmasdan o‘tkaza olmaydi (`400 dock_required`).
- **Dok holati (K29):** `FREE/BUSY` holatlar mashinasining yon ta’siri sifatida `docks.services.sync_dock_state` bilan yangilanadi. Dok `DOCK_ASSIGNED, CALLED, ARRIVED, RELEASE_STARTED` va `SUSPENDED` (dokli) arizalar uchun band. `RELEASED` dan boshlab, kelmaslik sababli navbat oxiriga o‘tkazilganda yoki bekor qilinganda bo‘shaydi. `MAINTENANCE` ni faqat SUPERVISOR qo‘yadi/olib tashlaydi (band dokni ta’mirga qo‘yib bo‘lmaydi); arizalar harakati uni o‘zgartirmaydi. `EXIT_CONFIRMED → AWAITING_PREP` (ikkinchi sikl) dokni bo‘shatadi.
- **Ustuvorlik:** `POST /api/requests/{id}/priority/` (0–9, SUPERVISOR); faqat tartibga ta’sir qiladi, `AuditLog` ga eski/yangi qiymat va sabab yoziladi; yakunlangan arizada `409`. "Qayta chaqirish" tugmasi 3-bosqichda (CALLED holati bilan).
- **Dispetcher API:** `GET /api/dispatcher/overview/` (KPI + dok kartalari) va `queue/` (faol navbat: `priority DESC, sort_at ASC`, har bir `AWAITING_DOCK` qator uchun mos bo‘sh doklar). Rollar: SUPERVISOR va ADMIN (ADMIN faqat o‘qiydi, K23). Javoblarda shaxsga doir maydonlar yo‘q (overview). KPI: kunlik ko‘rsatkichlar `queue_date` bo‘yicha, holat bo‘yicha sonlar barcha faol arizalar bo‘yicha; "o‘rtacha kutish" — dok kutayotgan va tayyorlanayotgan arizalarning ro‘yxatdan o‘tganidan beri vaqti.
- **Real vaqt:** `ws/dispatcher/` (SUPERVISOR, ADMIN), `ws/warehouse/` (WAREHOUSE, SUPERVISOR), `ws/dock/<code>/` (DOCK_AGENT, SUPERVISOR). Session autentifikatsiyasi + `AllowedHostsOriginValidator`. Hodisalar faqat id va holat tashiydi: `request.status`, `request.changed`, `warehouse.task`, `dock.state`. Mijoz yuborgan xabarlar e’tiborga olinmaydi. Frontend ulanishni qayta tiklaydi (1→15 s) va 15 soniyalik so‘rov bilan zaxiralangan. `CHANNEL_LAYER=memory` — Redis'siz lokal ishlash uchun (faqat bitta jarayon; prod rad etadi).
- **PWA:** `manifest.webmanifest` (boshlang‘ich sahifa `/warehouse`), 3 ta ikonka, minimal `sw.js` (faqat ilova qobig‘i va statik fayllar keshlanadi; `/api`, `/ws`, `/admin` hech qachon keshlanmaydi). Service worker faqat production build'da ro‘yxatdan o‘tadi.
- **Yangi kutubxonalar:** yo‘q.
- **Test muhiti:** WebSocket testlari `WebsocketCommunicator` bilan (`transaction=True`, PostgreSQL); jonli tekshiruvda haqiqiy brauzersiz Node `WebSocket` klienti ishlatildi.

## 2026-11-04 — 3-bosqich qarorlari

- **Chaqirish sharti (TZ 3.3):** `DOCK_ASSIGNED → CALLED` faqat uchala shart bajarilganda: (1) yuk tayyor (oxirgi ombor topshirig‘i `READY` yoki `HANDED_OVER`), (2) dok xizmatda (faol, ta’mirda emas), (3) dok xodimi tayyor. Guard holatlar mashinasida; javobda `blockers` ro‘yxati (`cargo_not_ready`, `dock_unavailable`, `agent_not_ready`, `no_dock`) — ekranlarda o‘zbekcha tushuntiriladi.
- **Avtomatik chaqirish (TZ 3.4):** dok belgilangach tizim darhol chaqiradi, agar hammasi tayyor bo‘lsa. Aks holda ariza `DOCK_ASSIGNED` da kutadi va xodim dokka kirganda (`checkin`) yoki davriy vazifa (har 30 s) tayyor ekanini topganda chaqiriladi. Smena boshlig‘i qo‘lda ham chaqira oladi (`POST /requests/{id}/call/`).
- **Dok xodimi tayyorligi (K27):** `POST /api/dock/checkin/` — bitta dokda bitta xodim, bitta xodim bitta dokda (boshqa dokka o‘tsa, oldingisi bo‘shaydi). Dokda mijoz (`CALLED/ARRIVED/RELEASE_STARTED`) bo‘lsa, `checkout` rad etiladi. Ta’mirdagi dokka kirib bo‘lmaydi. Har bir kirish/chiqish auditga yoziladi.
- **`CallEvent`:** har chaqiruv bitta yozuv; `attempt_no` ariza bo‘yicha uzluksiz o‘sadi. Takroriy chaqiruvda oldingisi `NO_SHOW`, mijoz kelganda `ARRIVED` (+ `arrived_at`) bo‘ladi.
- **Takroriy chaqiruv:** `max_recalls` (standart 2) bilan cheklangan; dok agenti (faqat o‘z dokida) yoki smena boshlig‘i qo‘lda, tizim esa taymer bilan chaqiradi. "Davra" — ariza navbat oxiriga o‘tkazilgandan keyin takroriy chaqiruvlar hisobi qaytadan boshlanadi.
- **Kelmaslik taymeri (TZ 5.1, K28):** `process_no_shows` har 30 s (Celery beat). Javobsiz chaqiruv (`no_show_timeout_min`, standart 10 daq) uchun: takroriy chaqiruv → (limit tugagach) `no_show_action=REQUEUE` bo‘lsa navbat oxiriga (`AWAITING_DOCK`, dok bo‘shaydi, `sort_at=now`, navbat raqami o‘zgarmaydi; `max_requeues`=1 marta) → aks holda `CANCELLED` (sabab bilan, tarix saqlanadi). `SUSPENDED` ariza taymerdan chetda. Hammasi `SystemSetting` dan; reglament buyurtmachi tasdig‘ini kutadi (K28).
- **`NO_SHOW` istisnosi:** navbat oxiriga o‘tkazilganda ochiq yozuv yaratiladi, mijoz kelganda avtomatik hal qilinadi (K17); bekor qilinganda hal qilingan holda yoziladi, oldingi ochiqlari ham yopiladi. Dispetcher KPI "Ochiq muammolar" `NO_SHOW` ni hisoblamaydi.
- **Kelish:** faqat o‘z dokidagi xodim (`arrive`); talonni skanerlash (QR, AWB yoki navbat raqami) mijozni aniqlaydi va chaqirilgan bo‘lsa kelganini qayd etadi. Yuk berishni boshlash (`RELEASE_STARTED`) 4-bosqichda.
- **SMS (TZ 7):** `SmsGateway` protokoli, `ConsoleSmsGateway` (logga yozadi), `MockSmsGateway` (testlar); `SMS_GATEWAY` orqali tanlanadi. Shablonlar: ro‘yxatga olish, chaqiruv, takroriy chaqiruv (`sms_on_recall` sozlamasi), holat (kelmadingiz / bekor qilindi). Matnda faqat talon raqami, dok va qisqa yo‘riqnoma — F.I.Sh., telefon, AWB yo‘q.
- **SMS yuborish:** `SmsMessage` yozuvi `QUEUED` bo‘lib saqlanadi, commitdan keyin Celery `send_sms` ga beriladi; xatoda qayta urinish (`sms_max_attempts`=3, `sms_retry_delay_sec`=30), keyin `FAILED`. Broker ishlamasa so‘rov buzilmaydi (xato logga yoziladi); `send_pending_sms` davriy vazifasi (har 60 s) urinilmagan xabarlarni yuboradi. Yetkazib berish hisobotlari (`DELIVERED`) shlyuz tanlangach.
- **Ommaviy ekranlar (TZ 3.4, qoida 7):** `/display/hall` (zal, 1920×1080) va `/display/led/<dok>`; login yo‘q. Kirish: `DISPLAY_ALLOWED_IPS` (IP/CIDR, standart faqat lokal) **yoki** ekranning o‘z tokeni (`?token=`, `DisplayScreen.token`, admin panelda ko‘rinadi). Token faqat o‘z ekraniga yaraydi (zal tokeni LED'ga, boshqa dok tokeni yaramaydi). Mijoz IP'si `REMOTE_ADDR` (proksi ortida ishonchli proksi sozlanishi kerak — 5-bosqich). Ma’lumot qat’iy ruxsat etilgan maydonlar ro‘yxati bilan: talon raqami, dok, davlat raqami, takroriy chaqiruv belgisi, dok holati; testlar shaxsga doir ma’lumot chiqmasligini tekshiradi.
- **Ommaviy ekran WebSocket:** `ws/display/hall/`, `ws/display/led/<dok>/` — faqat `{"event": "update"}` yuboradi (ma’lumot tashimaydi), ekran o‘zi API'dan qayta oladi; 10 s zaxira so‘rovi. Dok bo‘shaganda eski dokning LED ekrani ham yangilanadi.
- **Dok agenti ekrani:** dok tanlash → tayyor; joriy mijoz (talon, davlat raqami, yuk, vakil, izoh), taymer (qolgan vaqt), "Keldi" / "Qayta chaqirish", talonni skanerlash, ariza tarixi, keyingi navbat (dok toifalariga mos). Yuk berish tugmalari ("Yakunlash / Qisman / Muammo") 4-bosqichda.
- **Dispetcher:** "Chaqirish" (tayyor bo‘lmasa nima yetishmasligi ko‘rsatiladi) va "Qayta chaqirish" (qolgan limit bilan) tugmalari; dok kartasida xodim va tayyorligi.
- **Lokal ishlash (Docker/Redis yo‘q):** `CELERY_EAGER=1` (vazifalar joyida bajariladi), `CHANNEL_LAYER=memory`, davriy ishlar uchun `python manage.py run_timers` (`make timers`). Production uchun uchalasi ham taqiqlangan/ishlatilmaydi (prod `CELERY_EAGER` va `memory` ni rad etadi).
- **Test muhiti:** soat aniqligi Windows'da qo‘pol bo‘lishi mumkin — vaqtga bog‘liq testlar vaqtni aniq siljitadi (`age_call`), "kutish" ishlatilmaydi.
- **Yangi kutubxonalar:** yo‘q.

## 2026-11-04 — 4-bosqich qarorlari

- **Yuk berish (TZ 5.2):** dok agenti (faqat o‘z dokida) `release/start` (`ARRIVED → RELEASE_STARTED`, `ReleaseOperation` ochiladi), `release/progress` (shu safar berilgan o‘rinlar sonini belgilaydi, tuzatish mumkin; jami o‘rinlardan oshsa `409 release_exceeds`, ikkinchi himoya — DB trigger), `release/finish`, `release/partial`. Har bir `progress` auditga yoziladi.
- **To‘liq yakunlash:** faqat barcha o‘rinlar berilgan bo‘lsa; `RELEASED` (xodim) va darhol `AWAITING_CHECKPOINT` (tizim) bitta tranzaksiyada; operatsiya `finished_at` va `weight_released_kg` (berilgan o‘rinlarga mutanosib, xodim tarozida o‘lchagan bo‘lsa — shu qiymat) bilan yopiladi; dok bo‘shaydi.
- **Qisman berish:** sabab (`MISSING, DAMAGE, SHORTAGE, CUSTOMER, OTHER`) va izoh **majburiy**; `PARTIALLY_RELEASED` (sabab tarixda), so‘ng `AWAITING_CHECKPOINT`. TZ 5.2 maydonlari: jami / berilgan / berilmagan (`ExceptionRecord.pieces_affected`), sabab va izoh (`description`), sana-vaqt va mas’ul xodim. Ariza ochiq qoladi; ochiq `PARTIAL` yozuvi yaratiladi. 0 ta o‘rin berilgan holat ham qisman berish hisoblanadi.
- **Qoldiq (K14):** NO‘P chiqishni tasdiqlagach ariza `EXIT_CONFIRMED` da qoladi (tizim yopmaydi). Smena boshlig‘i qaror qiladi: (a) **qolganini tayyorlash** (`AWAITING_PREP`, yangi ombor topshirig‘i avtomatik, navbat raqami va talon o‘sha-o‘sha, ombor kartasida qolgan o‘rinlar ko‘rinadi, dok bo‘shaydi) yoki (b) **hujjatlashtirilgan sabab bilan yopish**. Ikkinchi turda faqat qoldiq o‘rinlar berilishi mumkin. Qoldiq to‘liq berilganda `PARTIAL` yozuvi avtomatik hal qilinadi (K17); sabab bilan yopilganda qaror matni uning yechimi bo‘ladi.
- **Avtomatik yopish:** `EXIT_CONFIRMED → CLOSED` (tizim) faqat hamma o‘rin berilgan va hal qilinmagan istisno yo‘q bo‘lsa (qoida 6, TZ 11 band 11): chiqish tasdiqlangandan keyin va har bir istisno hal qilingandan keyin urinadi. Qoldiq bilan yopishda ochiq `PARTIAL` to‘sqinlik qilmaydi (u qaror bilan hal bo‘ladi), boshqa ochiq istisnolar esa to‘sqinlik qiladi.
- **Holat-to‘qnashuvi xatolari 409:** `release_incomplete`, `release_not_partial`, `no_remainder`, `open_exceptions`, `close_with_remainder`, `resume_wrong_target`, `cancel_after_release` (oldin 400 edi).
- **Muammo (K16):** dok agenti (o‘z dokidagi mijoz, `CALLED/ARRIVED/RELEASE_STARTED`) yoki smena boshlig‘i `POST /requests/{id}/problems/` bilan `MISSING/DAMAGE/SHORTAGE/MISMATCH` qayd etadi; ariza holati o‘zgarmaydi.
- **Istisnolarni hal qilish:** `GET /api/exceptions/` (SUPERVISOR, ADMIN o‘qiydi; standart — ochiqlari, `NO_SHOW` hisobga olinmaydi) va `POST /api/exceptions/{id}/resolve/` (faqat SUPERVISOR, qaror matni majburiy, bir marta, auditga yoziladi). Hal qilingach: to‘xtab qolgan ombor topshirig‘i oldingi holatiga qaytadi (`READY` / `IN_PROGRESS` / `NEW`; agar boshqa ombor muammosi ochiq bo‘lsa — kutadi) va yopish urinib ko‘riladi.
- **NO‘P (TZ 5.4):** `checkpoint/scan` (QR, AWB yoki navbat raqami; har qanday holatdagi ariza uchun, `blocked_reason` bilan), `confirm`, `hold`, `overview` (kutayotganlar va bugungi o‘tishlar). Tasdiqlash faqat `AWAITING_CHECKPOINT` da; kiritilgan davlat raqami arizadagidan farq qilsa (ariza raqami bo‘sh bo‘lmasa) tasdiqlash rad etiladi (`409 plate_mismatch`) va xodim tafovutni qayd etishi kerak. Tekshiruv ro‘yxati (talon, raqam, o‘rinlar, hujjatlar) planshetda majburiy belgilanadi (server tekshirmaydi — bu xodimning vizual nazorati).
- **Tafovut (hold):** `ExceptionRecord(CHECKPOINT)` + `CheckpointPass(HELD)` + ariza `SUSPENDED` (sabab bilan) + smena boshlig‘iga real vaqtda xabar. Chiqishni qayta tiklash (`resume`) faqat `CHECKPOINT/MISMATCH` istisnolari hal qilingach mumkin (`409 checkpoint_unresolved`), so‘ng NO‘P qayta ko‘radi.
- **Qayta tiklash:** `POST /requests/{id}/resume/` (SUPERVISOR, sabab majburiy) to‘xtatilgan arizani to‘xtatishdan oldingi holatiga qaytaradi.
- **Real vaqt:** `ws/checkpoint/` (CHECKPOINT, SUPERVISOR); har bir holat o‘zgarishi va istisno o‘zgarishi NO‘P guruhiga ham yuboriladi.
- **Ekranlar:** dok agenti ekranida berish hisoblagichi (+/−, qo‘lda kiritish, "Hammasi"), "Yakunlash" (hamma o‘rin berilguncha o‘chiq), "Qisman berish" oynasi, "Muammo"; NO‘P planshet ekrani; dispetcherda "Qaror kutayotganlar" paneli (muammolar + hal qilish, to‘xtatilganlar + qayta tiklash, qoldig‘i bor arizalar + qolganini tayyorlash / sabab bilan yopish).
- **Yangi kutubxonalar:** yo‘q.

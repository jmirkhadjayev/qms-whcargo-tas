# Claude Code uchun boshlang‘ich prompt

> Foydalanish: shu papkani (`yuk-navbat/`) loyiha papkasi sifatida oching, terminalda `claude` ni ishga tushiring va quyidagi chiziq ostidagi matnni birinchi xabar sifatida yuboring. Keyingi bosqichlar uchun pastdagi qisqa promptlardan foydalaning.

---

Sen tajribali full-stack dasturchisan. Bu repozitoriyda aeroport yuk ombori uchun elektron navbat tizimini noldan quramiz.

**Avval o‘qi:** `CLAUDE.md` (loyiha qoidalari, texnologiyalar, domen qoidalari, holatlar jadvali, ekranlar), `docs/TZ.md` (texnik topshiriq), `docs/ER.md` (ma’lumotlar modeli). Ular bu loyihadagi yagona haqiqat manbai.

**Kod yozishdan oldin** menga quyidagilarni qisqa qilib ber va tasdiqlashimni kut:
1. TZ, ER va CLAUDE.md o‘rtasida ziddiyat yoki noaniqlik topgan bo‘lsang — ro‘yxati va har biri uchun taklifing.
2. 0- va 1-bosqich uchun aniq reja: qaysi fayllar, qaysi modellar, qaysi API endpointlar, qaysi testlar.

Tasdiqlaganimdan keyin quyidagilarni bajar.

## 0-bosqich — skelet

- `docker-compose.yml`: postgres:16, redis:7, backend (Django, ASGI — daphne yoki uvicorn), celery worker, celery beat, frontend (Vite dev server). Healthcheck'lar bilan. `.env.example`.
- Django loyihasi `backend/config` (settings: base/dev/prod), `CLAUDE.md` dagi app'lar bo‘sh holatda. `TIME_ZONE="Asia/Tashkent"`, `USE_TZ=True`, `LANGUAGE_CODE="uz"`.
- `accounts`: custom `User` (birinchi migratsiyadan oldin!), `Role`, JWT yoki session login (o‘zing tanla, sababini `docs/DECISIONS.md` ga yoz), rollar bo‘yicha DRF permission klasslari.
- drf-spectacular: `/api/schema/` va `/api/docs/`.
- Frontend: Vite + React + TS + Tailwind + React Router + TanStack Query. Login sahifasi, rolga qarab yo‘naltirish, umumiy layout (yuqori panel: logotip, bo‘limlar, sana-vaqt, foydalanuvchi). `src/i18n/uz.ts`.
- ruff, mypy, ESLint, Prettier, pytest sozlamalari. `Makefile` yoki `justfile`: `up`, `test`, `lint`, `migrate`, `seed`.
- GitHub Actions: lint + test.
- `seed` buyrug‘i: har bir roldan bitta foydalanuvchi, 8 ta dok (D-01…D-08), yuk toifalari (GEN, OVZ, DGR, PER, VAL), 3 ta smena, standart `SystemSetting` qiymatlari.

**Tayyor mezoni:** `docker compose up` → `http://localhost:5173` da login ishlaydi, har bir rol o‘z bo‘sh sahifasiga tushadi; `make test` va `make lint` yashil.

## 1-bosqich — yadro: ariza, holatlar mashinasi, ro‘yxatga olish, talon

- `docs/ER.md` dagi **barcha** modellar va migratsiyalar (keyingi bosqichlarniki ham — sxema bir marta to‘g‘ri qurilsin). Indekslar va constraint'lar: `UNIQUE(queue_date, queue_number)`, `qr_token` unique, faol arizalar uchun qisman indeks, `pieces_released` cheklovi.
- `RequestStatusHistory` va `AuditLog` uchun UPDATE/DELETE'ni taqiqlovchi PostgreSQL trigger (migratsiya ichida).
- Ruxsatnomasiz ariza yaratishni taqiqlovchi DB darajasidagi himoya (trigger) + service tekshiruvi.
- `cargo_queue/services/state_machine.py`: `CLAUDE.md` dagi jadval asosida, deklarativ (o‘tishlar jadvali + guard funksiyalar + rol tekshiruvi). API: `transition(request, to_status, user, reason=None)`. Har bir o‘tish: tranzaksiya, tarix yozuvi, audit, `on_commit` da WebSocket hodisasi.
- Navbat raqamini xavfsiz berish (parallel so‘rovlarda ham takrorlanmasligi testda isbotlansin).
- `integrations/permits.py`: `PermitProvider` protokoli, `MockPermitProvider` (AWB oxirgi raqami juft bo‘lsa — tasdiqlangan, toq bo‘lsa — rad etilgan; demo uchun), `ManualPermitProvider`.
- API: ruxsatnomani tekshirish (`POST /api/permits/check`), ariza yaratish, arizalar ro‘yxati (filtrlar bilan), bitta ariza + tarixi, talonni qayta chop etish, holat o‘tishi uchun umumiy endpoint.
- Talon: 80 mm uchun HTML/CSS chop etish sahifasi (`@page size: 80mm auto`), QR — `qr_token` dan.
- Frontend: **Ro‘yxatga olish ekrani** `CLAUDE.md` dagi tavsif va dizayn bo‘yicha to‘liq ishlaydi: AWB → tekshiruv → yashil/qizil banner → forma (validatsiya o‘zbekcha) → yaratish → talon chop etish oynasi; o‘ngda bugungi arizalar ro‘yxati.
- Django admin: barcha modellar (tarix va audit — faqat o‘qish).

**Testlar (kamida):**
- har bir ruxsat etilgan va 5+ taqiqlangan holat o‘tishi;
- har bir o‘tish tarix va audit yozuvini yaratadi;
- ruxsatnomasiz ariza yaratib bo‘lmaydi (service va DB darajasida alohida);
- navbat raqami har kuni 1 dan boshlanadi va parallel so‘rovlarda takrorlanmaydi;
- `RequestStatusHistory` ni o‘zgartirish/o‘chirish DB tomonidan rad etiladi;
- har bir endpoint uchun ruxsat etilgan va rad etilgan rol.

**Tayyor mezoni:** agent sifatida kirib, AWB kiritib, ariza yaratib, talonni chop etish mumkin; noto‘g‘ri AWB bilan ariza yaratilmaydi va sababi ko‘rsatiladi; barcha testlar yashil.

## Har bir bosqich oxirida

Qisqa hisobot ber: nima qilindi, `docs/DECISIONS.md` ga nima yozildi, qanday qo‘lda tekshirish mumkin (aniq qadamlar), keyingi bosqichda nima qilinadi. Keyin **to‘xta** va mening tasdig‘imni kut.

---

## Keyingi bosqichlar uchun promptlar

Har birini oldingi bosqich tasdiqlangandan keyin yuboring.

**2-bosqich:**
> `CLAUDE.md` va TZ 3.2–3.3 asosida 2-bosqichni bajar: ariza ro‘yxatga olinganda ombor topshirig‘ini avtomatik yaratish; ombor xodimi uchun mobil (PWA) ekran — topshiriqlar, "Boshlash / Tayyor / Muammo", skanerlash (kamera yoki USB skaner — klaviatura kiritishi); smena boshlig‘i uchun "Navbat va doklar" ekrani — KPI, dok kartalari, faol navbat jadvali, dok belgilash, ustuvorlik. Django Channels orqali real vaqt yangilanishi (guruhlar: `dispatcher`, `warehouse`, `dock.<code>`). Testlar bilan. Oxirida hisobot va to‘xta.

**3-bosqich:**
> TZ 3.4, 5.1 va 7 asosida 3-bosqichni bajar: dokka chaqirish (yuk, dok va xodim tayyorligi guard'i bilan), `CallEvent`, Celery beat orqali kelmaslik taymeri (`SystemSetting.no_show_timeout_min`) va qayta chaqiruv; `SmsGateway` protokoli + `ConsoleSmsGateway`, SMS Celery task'da qayta urinish bilan, `SmsMessage` jurnali; kiosk sahifalar — zal ekrani (1920×1080) va dok LED (`/display/led/<dock>`), login talab qilmaydi, faqat ruxsat etilgan IP yoki token bilan, shaxsga doir ma’lumot chiqarmaydi; dok agenti ekrani. Testlar bilan. Oxirida hisobot va to‘xta.

**4-bosqich:**
> TZ 5.2–5.4 asosida 4-bosqichni bajar: to‘liq va qisman yuk berish, `ExceptionRecord` (kamomad, shikast, tafovut, kelmaslik) va ularni hal qilish; NO‘P planshet ekrani — talon skanerlash, tekshiruv ro‘yxati, chiqishni tasdiqlash yoki tafovut qayd etish (ariza SUSPENDED, smena boshlig‘iga xabar); ochiq istisno bo‘lsa ariza yopilmasligi. Testlar bilan. Oxirida hisobot va to‘xta.

**5-bosqich:**
> TZ 8 va 10 asosida 5-bosqichni bajar: TZ 8.1 dagi 6 ta hisobot (`RequestStatusHistory` asosida SQL bilan hisoblash, katta davrlarda tez ishlashi uchun indekslar yoki materialized view), filtrlar, Excel/CSV/PDF eksport; hisobotlar ekrani; audit jurnali ko‘rinishi (admin); zaxira nusxa skripti (`pg_dump` + WAL arxiv bo‘yicha qo‘llanma `docs/OPERATIONS.md` da); production `docker-compose.prod.yml` (nginx, gunicorn/uvicorn, statik fayllar). TZ 11 dagi har bir qabul qilish mezoni uchun avtomatik test yoki `docs/ACCEPTANCE.md` da qo‘lda tekshirish qadami. Oxirida hisobot.

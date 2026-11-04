# Yuk navbati — loyiha qoidalari

Bu fayl loyihaning doimiy konteksti. Har bir ishni boshlashdan oldin shu faylga, `docs/TZ.md` va `docs/ER.md` ga amal qil.

## Loyiha nima

Islom Karimov nomidagi Toshkent xalqaro aeroporti yuk omborida import yuklari va pochtani berish uchun **elektron navbat tizimi**. Jarayon:

ro‘yxatga olish (agent, ruxsatnoma tekshiruvi) → talon (QR) → ombor yukni tayyorlaydi → smena boshlig‘i dok belgilaydi → mijoz LED-ekran va SMS orqali chaqiriladi → dokda yuk beriladi (to‘liq yoki qisman) → NO‘P (nazorat-o‘tkazish punkti) talonni skanerlab chiqishni tasdiqlaydi → ariza yopiladi → hisobotlar.

To‘liq talablar: `docs/TZ.md` (texnik topshiriq, o‘zbek tilida). Ma’lumotlar modeli: `docs/ER.md`.

## Texnologiyalar (o‘zgartirishdan oldin so‘ra)

- **Backend:** Python 3.12, Django 5.2 LTS, Django REST Framework, Django Channels (WebSocket), Celery, drf-spectacular (OpenAPI).
- **Ma’lumotlar bazasi:** PostgreSQL 16. **Kesh / navbat / pub-sub:** Redis 7.
- **Frontend:** React 18 + TypeScript + Vite, React Router, TanStack Query, Tailwind CSS. API klienti OpenAPI sxemasidan generatsiya qilinadi.
- **Testlar:** pytest, pytest-django, factory_boy (backend); Vitest + Testing Library (frontend).
- **Sifat:** ruff (lint + format), mypy (backend, asosiy modullar), ESLint + Prettier (frontend).
- **Ishga tushirish:** Docker Compose (postgres, redis, backend, celery worker, celery beat, frontend). Hammasi `docker compose up` bilan ishlashi kerak.

## Repozitoriy tuzilmasi

```
backend/
  config/            settings (base, dev, prod), urls, asgi, celery
  accounts/          User, Role, login, rollar bo‘yicha huquqlar
  cargo_queue/       QueueRequest, Consignee, ReleasePermit, CargoCategory, Shift, Ticket,
                     RequestStatusHistory, holatlar mashinasi (services/state_machine.py)
  warehouse/         WarehouseTask
  docks/             Dock, DockCategory, DisplayScreen, CallEvent, ReleaseOperation
  checkpoint/        CheckpointPass
  exceptions_app/    ExceptionRecord (kamomad, shikast, tafovut, kelmaslik)
  notifications/     SmsMessage, SMS adapterlari
  reports/           hisobot so‘rovlari, Excel/CSV/PDF eksport
  audit/             AuditLog, middleware/signal
  integrations/      AWERY, SMS-shlyuz, LED adapterlari (har birining mock varianti bor)
frontend/
  src/pages/         registration, dispatcher, dock, warehouse, checkpoint, reports, admin
  src/displays/      hall (zal ekrani), led (dok LED) — login talab qilmaydigan kiosk sahifalar
docs/                TZ.md, ER.md, DECISIONS.md (qabul qilingan qarorlar jurnali)
docker-compose.yml
```

## Til

- **Interfeys matnlari:** o‘zbek tili, lotin yozuvi (o‘ va g‘ uchun `‘` belgisi). Barcha matnlar bitta lug‘at faylida (`frontend/src/i18n/uz.ts`), keyinchalik rus tili qo‘shish oson bo‘lsin.
- **Kod, identifikatorlar, commit xabarlari:** ingliz tilida. **Izohlar:** ingliz tilida, qisqa.
- Foydalanuvchiga ko‘rinadigan backend xato xabarlari ham o‘zbek tilida.

## Domen qoidalari (buzilmasligi shart)

1. **Ruxsatnomasiz ariza yo‘q.** `QueueRequest` faqat `ReleasePermit.status == VERIFIED` bo‘lsa yaratiladi. Tekshiruv service qatlamida va PostgreSQL trigger yoki constraint orqali ikki marta qilinadi. Rad etilgan urinish `AuditLog` ga yoziladi (TZ 3.1).
2. **Holat faqat holatlar mashinasi orqali o‘zgaradi.** `cargo_queue/services/state_machine.py` — yagona joy. View, serializer, admin yoki signal `status` maydonini to‘g‘ridan-to‘g‘ri o‘zgartirmaydi. Har bir o‘tish bitta tranzaksiyada `RequestStatusHistory` yozuvini yaratadi va WebSocket hodisasini yuboradi (`transaction.on_commit`).
3. **Tarix o‘chirilmaydi.** `RequestStatusHistory` va `AuditLog` ga faqat yozuv qo‘shiladi (UPDATE/DELETE yo‘q, model darajasida ham, DB huquqlari darajasida ham). Arizalar o‘chirilmaydi — `CANCELLED` holatiga o‘tkaziladi.
4. **Navbat raqami** har kuni (Asia/Tashkent bo‘yicha) 1 dan boshlanadi: `UNIQUE(queue_date, queue_number)`. Raqam poyga holatisiz (race condition) beriladi — `select_for_update` yoki PostgreSQL sequence/advisory lock.
5. **Qisman berish:** `sum(ReleaseOperation.pieces_released) <= pieces_total`. Sabab va izoh majburiy. Ariza ochiq qoladi.
6. **Hal qilinmagan `ExceptionRecord` bo‘lsa, ariza `CLOSED` ga o‘ta olmaydi** (TZ 5.4, 11).
7. **Ommaviy ekranlarga** (zal, LED) faqat talon raqami, dok kodi va davlat raqami chiqadi. F.I.Sh., telefon, STIR hech qachon (TZ 3.4).
8. **Vaqt:** bazada `timestamptz`, `TIME_ZONE = "Asia/Tashkent"`, `USE_TZ = True`.
9. **Sozlanadigan qiymatlar** (kelmaslik kutish vaqti — standart 10 daqiqa, qayta chaqiruvlar soni va h.k.) kodga yozilmaydi, `SystemSetting` jadvalidan o‘qiladi.

### Ariza holatlari va o‘tishlar

| Kod | O‘zbekcha | Qayerga o‘tish mumkin | Kim |
|---|---|---|---|
| REGISTERED | Ro‘yxatdan o‘tkazildi | AWAITING_PREP | tizim (ombor topshirig‘i yaratilganda) |
| AWAITING_PREP | Tayyorlashni kutmoqda | PREP_STARTED | ombor |
| PREP_STARTED | Tayyorlash boshlandi | CARGO_READY | ombor |
| CARGO_READY | Yuk tayyorlandi | AWAITING_DOCK | tizim |
| AWAITING_DOCK | Dok belgilanishini kutmoqda | DOCK_ASSIGNED | smena boshlig‘i |
| DOCK_ASSIGNED | Dok belgilandi | CALLED | smena boshlig‘i / tizim (yuk, dok va xodim tayyor bo‘lsa) |
| CALLED | Mijoz chaqirildi | CALLED (qayta chaqiruv), ARRIVED, AWAITING_DOCK yoki CANCELLED (kelmaslik reglamenti bo‘yicha) | dok agenti / tizim |
| ARRIVED | Mijoz yetib keldi | RELEASE_STARTED | dok agenti |
| RELEASE_STARTED | Yuk berish boshlandi | RELEASED, PARTIALLY_RELEASED | dok agenti |
| RELEASED | Yuk berish yakunlandi | AWAITING_CHECKPOINT | tizim |
| PARTIALLY_RELEASED | Qisman berildi | AWAITING_CHECKPOINT | tizim |
| AWAITING_CHECKPOINT | NO‘Pda tasdiqlashni kutmoqda | EXIT_CONFIRMED, SUSPENDED (tafovut) | NO‘P |
| EXIT_CONFIRMED | Chiqib ketish tasdiqlandi | CLOSED; qisman berilgan bo‘lsa — qolgan qism uchun AWAITING_PREP | tizim / smena boshlig‘i |
| SUSPENDED | To‘xtatib turildi | oldingi holatga qaytish (sabab bilan) | smena boshlig‘i |
| CANCELLED | Bekor qilindi | — (yakuniy) | — |
| CLOSED | Yopildi | faqat ADMIN qayta ochadi, sabab majburiy (TZ 10) | admin |

Qo‘shimcha: RELEASE_STARTED dan oldingi har qanday holatdan → CANCELLED (smena boshlig‘i, sabab majburiy). Yakuniy bo‘lmagan har qanday holatdan → SUSPENDED (smena boshlig‘i). Qisman berishdan keyingi oqim — taklif; buyurtmachi tasdiqlagach `docs/DECISIONS.md` ga yoziladi.

### Rollar

`REG_AGENT` (ro‘yxatga olish), `WAREHOUSE` (ombor), `DOCK_AGENT` (dok), `SUPERVISOR` (smena boshlig‘i), `CHECKPOINT` (NO‘P), `MANAGER` (faqat hisobotlar), `ADMIN`. Har bir API endpoint qaysi rollarga ruxsat berishi aniq yoziladi va test bilan tekshiriladi.

## Tashqi tizimlar — har doim adapter orqali

`integrations/` da har biri uchun interfeys (Protocol) + `Mock...` + haqiqiy implementatsiya joyi:
- `PermitProvider` — AWERY (API hali noma’lum → hozircha `MockPermitProvider` va `ManualPermitProvider`: vakolatli xodim qo‘lda tasdiqlaydi, tarix saqlanadi).
- `SmsGateway` — mahalliy SMS-shlyuz (hozircha `ConsoleSmsGateway` / `MockSmsGateway`). SMS faqat Celery task orqali, qayta urinish bilan.
- `LedDisplayDriver` — hozircha brauzer kiosk sahifasi (`/display/led/<dock>`), WebSocket orqali yangilanadi.
Qaysi adapter ishlatilishi `.env` orqali tanlanadi.

## Ish uslubi

- Ishni **kichik bosqichlarga** bo‘l. Har bosqich oxirida: testlar o‘tadi, `docker compose up` ishlaydi, qisqa hisobot yoz (nima qilindi, nima qoldi, qanday tekshirish mumkin) va keyingi bosqichdan oldin **to‘xta**.
- Biznes mantiq `services/` da, view'lar yupqa. Modellar `docs/ER.md` ga mos.
- Har bir domen qoidasi (yuqoridagi 1–9) va har bir holat o‘tishi uchun test bo‘lsin, shu jumladan **taqiqlangan** o‘tishlar uchun ham.
- TZ da aniq bo‘lmagan joyda o‘zing qaror qabul qil, lekin uni `docs/DECISIONS.md` ga sana va sabab bilan yoz.
- Maxfiy ma’lumotlar faqat `.env` da; `.env.example` repozitoriyda bo‘ladi.
- Yangi kutubxona qo‘shishdan oldin sababini ayt.
- Commit'lar kichik va mazmunli (`feat(queue): ...`, `test(...)`, `fix(...)`).

## Ekranlar

Dizayn maketlari (9 ta ekran) claude.ai'da: https://claude.ai/artifact/KV8xwGjk8iwqgiZaZvWwnh — vizual uslub: to‘q ko‘k-qora (#14202B) yuqori panel, sariq urg‘u (#F2A900), ochiq kulrang fon (#EEF1F4), IBM Plex Sans / IBM Plex Mono, raqamlar monospace.

1. **Ro‘yxatga olish** (`REG_AGENT`): AWB kiritish → "Ruxsatnomani tekshirish" → yashil/qizil natija → forma (yuk oluvchi, vakil, telefon, o‘rinlar, vazn, davlat raqami, toifa, izoh) → "Ro‘yxatga olish va talon chop etish". O‘ngda bugungi arizalar.
2. **Navbat va doklar** (`SUPERVISOR`): KPI qatori, 8 ta dok kartasi (bo‘sh/band/ta’mirda), faol navbat jadvali (dok belgilash, qayta chaqirish, ustuvorlik). Real vaqtda yangilanadi.
3. **Dok** (`DOCK_AGENT`): joriy talon, yuk ma’lumotlari, talonni skanerlash, berilgan o‘rinlar, "Yakunlash / Qisman berish / Muammo", ariza tarixi, keyingi navbat.
4. **Hisobotlar** (`MANAGER`, `SUPERVISOR`): filtrlar (davr, smena, dok, toifa), KPI, bosqichlar bo‘yicha o‘rtacha vaqt, doklar jadvali, Excel/CSV/PDF.
5. **Zal ekrani** (kiosk, 1920×1080): chaqirilganlar (talon, dok, davlat raqami) va tayyorlanayotganlar.
6. **Dok LED** (kiosk): talon raqami va davlat raqami.
7. **Talon** (80 mm termoprinter): aeroport nomi, talon raqami, AWB, o‘rinlar, vazn, davlat raqami, vaqt, QR (`qr_token`).
8. **Ombor** (`WAREHOUSE`, mobil/TSD, PWA): topshiriq kartalari, "Boshlash / Tayyor / Muammo", skanerlash.
9. **NO‘P** (`CHECKPOINT`, planshet): talonni skanerlash → tekshiruv ro‘yxati → "Chiqishni tasdiqlash" yoki "Tafovut bor".

# Ma’lumotlar bazasi modeli (ER)

PostgreSQL 16. Jadval va ustun nomlari — kodda shu nomlar ishlatiladi. Bu model boshlang‘ich taklif: kod yozish jarayonida asosli o‘zgartirish mumkin, lekin har bir o‘zgarish shu faylda ham yangilanishi kerak.

## Umumiy ko‘rinish

```mermaid
erDiagram
  roles ||--o{ users : "rol"
  users ||--o{ queue_requests : "ro‘yxatga oladi"
  consignees ||--o{ queue_requests : "yuk oluvchi"
  release_permits ||--o{ queue_requests : "ruxsatnoma"
  cargo_categories ||--o{ queue_requests : "toifa"
  shifts ||--o{ queue_requests : "smena"
  docks |o--o{ queue_requests : "belgilangan dok"
  queue_requests ||--o{ tickets : "talon"
  queue_requests ||--o{ request_status_history : "holatlar tarixi"
  queue_requests ||--o{ warehouse_tasks : "ombor topshirig‘i"
  queue_requests ||--o{ call_events : "chaqiruv"
  queue_requests ||--o{ release_operations : "yuk berish"
  queue_requests ||--o{ exceptions : "istisno"
  queue_requests ||--o{ checkpoint_passes : "NO‘P"
  queue_requests ||--o{ sms_messages : "SMS"
  docks ||--o{ dock_categories : ""
  cargo_categories ||--o{ dock_categories : ""
  docks ||--o{ display_screens : "LED-ekran"
  docks ||--o{ call_events : ""
  docks ||--o{ release_operations : ""
  users ||--o{ audit_log : "harakat"
```

## 1. Ariza va ro‘yxatga olish

```mermaid
erDiagram
  consignees ||--o{ queue_requests : "yuk oluvchi"
  release_permits ||--o{ queue_requests : "ruxsatnoma"
  cargo_categories ||--o{ queue_requests : "toifa"
  shifts ||--o{ queue_requests : "smena"
  users ||--o{ queue_requests : "agent"
  queue_requests ||--o{ tickets : "talon"
  queue_requests ||--o{ request_status_history : "holatlar"
  users ||--o{ request_status_history : "kim o‘zgartirdi"

  queue_requests {
    bigint id PK
    date queue_date UK "navbat sanasi"
    int queue_number UK "kun ichida noyob"
    varchar awb_number "aviayuk xati"
    bigint consignee_id FK
    bigint permit_id FK "tasdiqlangan ruxsatnoma"
    bigint category_id FK
    bigint shift_id FK
    bigint dock_id FK "nullable"
    int pieces_total "yuk o‘rinlari"
    numeric weight_kg
    varchar vehicle_plate "davlat raqami"
    varchar sms_phone
    varchar status "16 holatdan biri"
    smallint priority "0 oddiy"
    timestamptz sort_at "navbat tartibi: priority DESC, sort_at ASC (K8)"
    varchar representative_name "vakil, har tashrifda (K22)"
    varchar qr_token UK "talondagi kod"
    text notes
    bigint created_by FK
    timestamptz registered_at
    timestamptz closed_at
  }
  queue_counters {
    date queue_date PK
    int last_number "kunlik hisoblagich (K7)"
  }
  consignees {
    bigint id PK
    varchar name "korxona yoki shaxs"
    varchar tin "STIR"
    varchar representative_name "vakil"
    varchar phone
    timestamptz created_at
  }
  release_permits {
    bigint id PK
    varchar awb_number
    varchar permit_number
    varchar source "AWERY, MANUAL yoki MOCK (K5)"
    varchar status "VERIFIED, INVALID, REVOKED"
    bigint verified_by FK "qo‘lda tasdiqlaganda"
    timestamptz verified_at
    timestamptz valid_until
    jsonb raw_payload "tashqi tizim javobi"
  }
  cargo_categories {
    bigint id PK
    varchar code UK "GEN, OVZ, DGR, PER, VAL"
    varchar name
    bool special_handling
    smallint default_priority
  }
  shifts {
    bigint id PK
    varchar name
    time starts_at
    time ends_at
  }
  tickets {
    bigint id PK
    bigint request_id FK
    timestamptz printed_at
    bigint printed_by FK
    bool is_reprint
  }
  request_status_history {
    bigint id PK
    bigint request_id FK
    varchar from_status
    varchar to_status
    bigint changed_by FK "null bo‘lsa tizim"
    text reason
    timestamptz changed_at
  }
  users {
    bigint id PK
    varchar full_name
  }
```

## 2. Ombor, dok va NO‘P

```mermaid
erDiagram
  queue_requests ||--o{ warehouse_tasks : "topshiriq"
  queue_requests ||--o{ call_events : "chaqiruv"
  queue_requests ||--o{ release_operations : "yuk berish"
  queue_requests ||--o{ exceptions : "istisno"
  queue_requests ||--o{ checkpoint_passes : "NO‘P"
  docks ||--o{ call_events : ""
  docks ||--o{ release_operations : ""
  docks ||--o{ display_screens : "ekran"
  docks ||--o{ dock_categories : ""
  cargo_categories ||--o{ dock_categories : "ruxsat etilgan"

  queue_requests {
    bigint id PK
    int queue_number
    varchar status
  }
  warehouse_tasks {
    bigint id PK
    bigint request_id FK
    bigint assigned_to FK "ombor xodimi"
    varchar storage_location "ombordagi joyi"
    varchar status "NEW, IN_PROGRESS, READY, HANDED_OVER, PROBLEM"
    timestamptz created_at
    timestamptz started_at
    timestamptz ready_at
    timestamptz handed_over_at "dokka topshirildi"
  }
  docks {
    bigint id PK
    varchar code UK "D-01"
    varchar name
    varchar state "FREE, BUSY, MAINTENANCE"
    bool is_active
    bigint current_agent_id FK "nullable, dokdagi agent (K27)"
    timestamptz agent_ready_at "xodim tayyor (K27)"
  }
  dock_categories {
    bigint id PK "surrogate; UNIQUE(dock_id, category_id)"
    bigint dock_id FK
    bigint category_id FK
  }
  cargo_categories {
    bigint id PK
    varchar code
  }
  display_screens {
    bigint id PK
    bigint dock_id FK "null bo‘lsa umumiy ekran"
    varchar kind "DOCK_LED yoki HALL"
    varchar address "IP yoki port"
    varchar protocol "BROWSER, TCP, RS485"
    timestamptz last_seen_at
  }
  call_events {
    bigint id PK
    bigint request_id FK
    bigint dock_id FK
    smallint attempt_no "1 birinchi, 2+ takroriy"
    bigint called_by FK
    timestamptz called_at
    timestamptz arrived_at "mijoz keldi"
    varchar outcome "ARRIVED, NO_SHOW, PENDING"
  }
  release_operations {
    bigint id PK
    bigint request_id FK
    bigint dock_id FK
    bigint agent_id FK
    timestamptz started_at
    timestamptz finished_at
    int pieces_released "berilgan o‘rinlar"
    numeric weight_released_kg
  }
  exceptions {
    bigint id PK
    bigint request_id FK
    varchar kind "MISSING, DAMAGE, SHORTAGE, MISMATCH, PARTIAL, NO_SHOW, CHECKPOINT (jadval nomi: exceptions, model: ExceptionRecord)"
    int pieces_affected
    text description
    bigint reported_by FK
    timestamptz reported_at
    bigint resolved_by FK
    timestamptz resolved_at
    text resolution "qaror"
  }
  checkpoint_passes {
    bigint id PK
    bigint request_id FK
    bigint officer_id FK "NO‘P xodimi"
    timestamptz scanned_at
    varchar plate_observed "haqiqiy raqam"
    varchar result "APPROVED yoki HELD"
    timestamptz exit_confirmed_at
  }
```

## 3. Foydalanuvchilar, SMS va audit

```mermaid
erDiagram
  roles ||--o{ users : "rol"
  users ||--o{ audit_log : "harakat"
  users ||--o{ system_settings : "o‘zgartirdi"
  queue_requests ||--o{ sms_messages : "xabarnoma"

  roles {
    bigint id PK
    varchar code UK "REG_AGENT, WAREHOUSE, DOCK_AGENT, CHECKPOINT, SUPERVISOR, MANAGER, ADMIN"
    varchar name
  }
  users {
    bigint id PK
    varchar username UK
    varchar password "Django xeshi (K4)"
    varchar full_name
    bigint role_id FK
    bool is_active
    timestamptz last_login "Django nomi (K4)"
    timestamptz created_at
  }
  audit_log {
    bigint id PK
    bigint user_id FK "nullable (K6)"
    varchar action "CREATE, UPDATE, LOGIN, LOGIN_FAILED, EXPORT, TRANSITION, PERMIT_REJECTED, REOPEN, PRINT, REPRINT"
    varchar entity "jadval nomi"
    bigint entity_id "nullable (K6)"
    jsonb old_value
    jsonb new_value
    inet ip_address
    timestamptz created_at
  }
  sms_messages {
    bigint id PK
    bigint request_id FK
    varchar phone
    varchar template "REGISTERED, CALLED, RECALL, STATUS"
    text body
    varchar provider_msg_id "shlyuz ID"
    varchar status "QUEUED, SENT, DELIVERED, FAILED"
    smallint attempts
    timestamptz sent_at
    timestamptz delivered_at
    text error
  }
  system_settings {
    varchar key PK "masalan no_show_timeout_min"
    jsonb value "10"
    bigint updated_by FK
    timestamptz updated_at
  }
  queue_requests {
    bigint id PK
  }
```

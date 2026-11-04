from django.db import models


class RoleCode(models.TextChoices):
    REG_AGENT = "REG_AGENT", "Ro‘yxatga olish agenti"
    WAREHOUSE = "WAREHOUSE", "Ombor xodimi"
    DOCK_AGENT = "DOCK_AGENT", "Dok agenti"
    SUPERVISOR = "SUPERVISOR", "Smena boshlig‘i"
    CHECKPOINT = "CHECKPOINT", "NO‘P xodimi"
    MANAGER = "MANAGER", "Rahbar (hisobotlar)"
    ADMIN = "ADMIN", "Administrator"

import datetime as dt
import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import Role, SystemSetting, User
from accounts.roles import RoleCode
from accounts.settings_store import DEFAULTS
from cargo_queue.models import CargoCategory, Shift
from docks.models import DisplayScreen, Dock, DockCategory, ScreenKind

# One demo user per role. Passwords come from SEED_PASSWORD (.env); dev only.
DEMO_USERS = {
    RoleCode.REG_AGENT: ("reg_agent", "Ro‘yxatga olish agenti"),
    RoleCode.WAREHOUSE: ("warehouse", "Ombor xodimi"),
    RoleCode.DOCK_AGENT: ("dock_agent", "Dok agenti"),
    RoleCode.SUPERVISOR: ("supervisor", "Smena boshlig‘i"),
    RoleCode.CHECKPOINT: ("checkpoint", "NO‘P xodimi"),
    RoleCode.MANAGER: ("manager", "Rahbar"),
    RoleCode.ADMIN: ("admin", "Administrator"),
}


CATEGORIES = [
    # code, name, special_handling, default_priority
    ("GEN", "Umumiy yuk", False, 0),
    ("OVZ", "O‘ta katta o‘lchamli yuk", True, 0),
    ("DGR", "Xavfli yuk", True, 0),
    ("PER", "Tez buziladigan yuk", True, 1),
    ("VAL", "Qimmatbaho yuk", True, 0),
]
SHIFTS = [
    ("1-smena", dt.time(8, 0), dt.time(16, 0)),
    ("2-smena", dt.time(16, 0), dt.time(0, 0)),
    ("3-smena", dt.time(0, 0), dt.time(8, 0)),
]
# Demo mapping only: every dock takes GEN; special categories go to a few docks.
DOCK_SPECIAL = {
    "D-01": ["OVZ"],
    "D-02": ["OVZ", "VAL"],
    "D-03": ["DGR"],
    "D-04": ["PER"],
    "D-05": ["VAL"],
}


class Command(BaseCommand):
    help = "Create demo data: roles, one user per role, default system settings. Idempotent."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Seed faqat dev rejimida ishlaydi (DEBUG=True).")
        password = os.environ.get("SEED_PASSWORD")
        if not password:
            raise CommandError("SEED_PASSWORD muhit o‘zgaruvchisi o‘rnatilmagan (.env).")

        with transaction.atomic():
            for role_code in RoleCode:
                Role.objects.update_or_create(code=role_code, defaults={"name": role_code.label})
            for role_code, (username, full_name) in DEMO_USERS.items():
                role = Role.objects.get(code=role_code)
                user, created = User.objects.get_or_create(
                    username=username, defaults={"full_name": full_name, "role": role}
                )
                if created:
                    user.set_password(password)
                    user.save(update_fields=["password"])
            for key, value in DEFAULTS.items():
                SystemSetting.objects.get_or_create(key=key, defaults={"value": value})

            categories = {}
            for code, name, special, priority in CATEGORIES:
                categories[code], _ = CargoCategory.objects.update_or_create(
                    code=code,
                    defaults={
                        "name": name,
                        "special_handling": special,
                        "default_priority": priority,
                    },
                )
            for name, starts, ends in SHIFTS:
                Shift.objects.update_or_create(
                    name=name, defaults={"starts_at": starts, "ends_at": ends}
                )
            DisplayScreen.objects.get_or_create(dock=None, kind=ScreenKind.HALL)
            for number in range(1, 9):
                dock_code = f"D-{number:02d}"
                dock, _ = Dock.objects.get_or_create(
                    code=dock_code, defaults={"name": f"Dok {number}"}
                )
                DisplayScreen.objects.get_or_create(dock=dock, kind=ScreenKind.DOCK_LED)
                for cat_code in ["GEN", *DOCK_SPECIAL.get(dock_code, [])]:
                    DockCategory.objects.get_or_create(dock=dock, category=categories[cat_code])
        self.stdout.write(self.style.SUCCESS("Seed tayyor."))

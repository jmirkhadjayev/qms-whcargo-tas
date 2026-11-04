from __future__ import annotations

from typing import Any

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models

from .roles import RoleCode


class Role(models.Model):
    code = models.CharField(max_length=20, unique=True, choices=RoleCode.choices)
    name = models.CharField(max_length=100)

    class Meta:
        db_table = "roles"
        ordering = ["id"]

    def __str__(self) -> str:
        return self.code


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def create_user(self, username: str, password: str | None = None, **extra: Any) -> User:
        if not username:
            raise ValueError("username is required")
        if "role" not in extra:
            raise ValueError("role is required")
        user = self.model(username=username, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username: str, password: str | None = None, **extra: Any) -> User:
        role, _ = Role.objects.get_or_create(
            code=RoleCode.ADMIN, defaults={"name": RoleCode.ADMIN.label}
        )
        extra["role"] = role
        return self.create_user(username, password, **extra)


class User(AbstractBaseUser):
    """Custom user (first migration). Django's `password` / `last_login` replace ER names (K4)."""

    username = models.CharField(max_length=150, unique=True)
    full_name = models.CharField(max_length=255)
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="users")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        db_table = "users"

    def __str__(self) -> str:
        return f"{self.username} ({self.role.code})"

    # Django admin access: only an active ADMIN-role user (decision K23).
    @property
    def is_staff(self) -> bool:
        return self.is_active and self.role.code == RoleCode.ADMIN

    @property
    def is_superuser(self) -> bool:
        return self.is_staff

    def has_perm(self, perm: str, obj: Any = None) -> bool:
        return self.is_staff

    def has_module_perms(self, app_label: str) -> bool:
        return self.is_staff


class SystemSetting(models.Model):
    """Runtime-configurable values (domain rule 9). Read through accounts.settings_store."""

    key = models.CharField(max_length=100, primary_key=True)
    value = models.JSONField()
    updated_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "system_settings"

    def __str__(self) -> str:
        return self.key

"""Append-only models: no UPDATE / DELETE through the ORM (the DB trigger enforces it too)."""

from typing import Any

from django.db import models


class AppendOnlyError(Exception):
    """Raised when code tries to modify or delete an append-only record."""


class AppendOnlyQuerySet(models.QuerySet):
    def update(self, **kwargs: Any):
        raise AppendOnlyError("Yozuvni o‘zgartirib bo‘lmaydi.")

    def delete(self):
        raise AppendOnlyError("Yozuvni o‘chirib bo‘lmaydi.")

    def bulk_update(self, *args: Any, **kwargs: Any):
        raise AppendOnlyError("Yozuvni o‘zgartirib bo‘lmaydi.")


class AppendOnlyModel(models.Model):
    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise AppendOnlyError("Yozuvni o‘zgartirib bo‘lmaydi.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any):
        raise AppendOnlyError("Yozuvni o‘chirib bo‘lmaydi.")

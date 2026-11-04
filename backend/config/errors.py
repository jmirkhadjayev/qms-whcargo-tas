"""Domain-level errors that map to a clean API response (code + Uzbek message)."""

from typing import Any


class DomainError(Exception):
    """A business-rule violation. `message` is user-facing (Uzbek)."""

    status_code = 400

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int | None = None,
        extra: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.extra = extra or {}

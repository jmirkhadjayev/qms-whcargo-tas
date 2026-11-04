from .base import *  # noqa: F403
from .base import BASE_DIR, env_bool

DEBUG = True

# Local smoke-testing without Docker only. PostgreSQL is mandatory from stage 1 (DB triggers).
if env_bool("USE_SQLITE", False):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(BASE_DIR / "db.sqlite3"),
        }
    }

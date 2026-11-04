"""Base settings shared by all environments. Secrets come from the environment only."""

import os
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise RuntimeError(f"Environment variable {name} is required")
    return value


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


SECRET_KEY = env("DJANGO_SECRET_KEY", "insecure-dev-key-change-me")
DEBUG = False
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "http://localhost:5173")

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "channels",
    "rest_framework",
    "drf_spectacular",
    # project apps
    "accounts",
    "cargo_queue",
    "warehouse",
    "docks",
    "checkpoint",
    "exceptions_app",
    "notifications",
    "reports",
    "audit",
    "integrations",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", "yuk_navbat"),
        "USER": env("POSTGRES_USER", "yuk_navbat"),
        "PASSWORD": env("POSTGRES_PASSWORD", "yuk_navbat"),
        "HOST": env("POSTGRES_HOST", "localhost"),
        "PORT": env("POSTGRES_PORT", "5432"),
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

# Time: store timestamptz, operate in Tashkent time (domain rule 8).
LANGUAGE_CODE = "uz"
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Redis: cache, Channels layer, Celery broker.
REDIS_URL = env("REDIS_URL", "redis://localhost:6379/0")
# `memory` works inside a single process only: for local development without Redis.
CHANNEL_LAYER = env("CHANNEL_LAYER", "redis")  # redis | memory
CHANNEL_LAYERS: dict[str, dict[str, Any]]
if CHANNEL_LAYER == "memory":
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
else:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [REDIS_URL]},
        }
    }
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TIMEZONE = TIME_ZONE
# Eager mode runs tasks inline: for local development without Redis / a Celery worker.
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_EAGER", False)

# Session auth (decision K25): cookie + CSRF, same origin via the Vite proxy / nginx.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 12

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_RATES": {"login": "10/min"},
    "EXCEPTION_HANDLER": "config.exception_handler.api_exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Yuk navbati API",
    "DESCRIPTION": "Aeroport yuk ombori uchun elektron navbat tizimi",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_NAME_OVERRIDES": {"RequestStatusEnum": "cargo_queue.statuses.RequestStatus"},
}

AIRPORT_NAME = env("AIRPORT_NAME", "Islom Karimov nomidagi Toshkent xalqaro aeroporti")

# Periodic jobs (Celery beat): the no-show timer and the retry of calls that were not ready.
CELERY_BEAT_SCHEDULE = {
    "process-no-shows": {"task": "docks.process_no_shows", "schedule": 30.0},
    "call-waiting-requests": {"task": "docks.call_waiting_requests", "schedule": 30.0},
    "send-pending-sms": {"task": "notifications.send_pending_sms", "schedule": 60.0},
}

# Kiosk screens (hall / dock LED) need no login: they are reached from these networks, or with
# the screen's own token. Comma-separated IPs or CIDR blocks.
DISPLAY_ALLOWED_IPS = env_list("DISPLAY_ALLOWED_IPS", "127.0.0.1,::1")

# Integration adapters are chosen via .env (see CLAUDE.md "Tashqi tizimlar").
PERMIT_PROVIDER = env("PERMIT_PROVIDER", "mock")  # mock | manual | awery
SMS_GATEWAY = env("SMS_GATEWAY", "console")  # console | mock
LED_DRIVER = env("LED_DRIVER", "browser")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}

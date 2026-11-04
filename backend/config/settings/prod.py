from .base import *  # noqa: F403
from .base import CHANNEL_LAYER, PERMIT_PROVIDER, SECRET_KEY, env_bool

DEBUG = False

if SECRET_KEY.startswith("insecure"):
    raise RuntimeError("DJANGO_SECRET_KEY must be set in production")
if PERMIT_PROVIDER == "mock":
    raise RuntimeError("PERMIT_PROVIDER=mock is not allowed in production")
if CHANNEL_LAYER == "memory":
    raise RuntimeError("CHANNEL_LAYER=memory is not allowed in production (use redis)")
if env_bool("CELERY_EAGER", False):
    raise RuntimeError("CELERY_EAGER is not allowed in production (run a Celery worker)")
if env_bool("USE_SQLITE", False):
    raise RuntimeError("USE_SQLITE is not allowed in production")

SESSION_COOKIE_SECURE = env_bool("COOKIE_SECURE", True)
CSRF_COOKIE_SECURE = env_bool("COOKIE_SECURE", True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

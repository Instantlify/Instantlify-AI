import base64
import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-secret-not-for-deployment")
os.environ.setdefault("FIELD_ENCRYPTION_KEYS", base64.urlsafe_b64encode(b"0" * 32).decode())
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from .base import *  # noqa: E402, F403

ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CHANNEL_ADAPTER_MODE = "fake"
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

import base64
import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-secret-not-for-deployment")
os.environ.setdefault("FIELD_ENCRYPTION_KEYS", base64.urlsafe_b64encode(b"0" * 32).decode())
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from .base import *  # noqa: E402, F403

ALLOWED_HOSTS = DynamicAllowedHosts(["testserver", "localhost", "127.0.0.1"])  # noqa: F405
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CHANNEL_ADAPTER_MODE = "fake"
ALLOW_TEST_CHANNELS = False
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

# Compose supplies deployment env vars to the test container. Tests opt into mocked
# Stripe credentials explicitly; never inherit a real key for metrics or audit jobs.
STRIPE_SECRET_KEY = ""
STRIPE_WEBHOOK_SECRET = ""

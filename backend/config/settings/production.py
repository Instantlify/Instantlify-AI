from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

if DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":  # noqa: F405
    raise ImproperlyConfigured("Production requires PostgreSQL")
if not all(origin.startswith("https://") for origin in CSRF_TRUSTED_ORIGINS):  # noqa: F405
    raise ImproperlyConfigured("Production requires HTTPS CSRF_TRUSTED_ORIGINS")

if len(SECRET_KEY) < 50:  # noqa: F405
    raise ImproperlyConfigured(
        "Production requires a random DJANGO_SECRET_KEY of at least 50 characters"
    )
if CHANNEL_ADAPTER_MODE == "fake":  # noqa: F405
    raise ImproperlyConfigured("Fake channel adapters are forbidden in production")
if "localhost" in ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:  # noqa: F405
    raise ImproperlyConfigured("Set explicit production ALLOWED_HOSTS")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
# Only a trusted reverse proxy may reach Django; it must overwrite this header.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

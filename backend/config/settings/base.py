import os
from datetime import timedelta
from pathlib import Path

import dj_database_url
from cryptography.fernet import Fernet
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def required(name):
    value = os.environ.get(name)
    if not value:
        raise ImproperlyConfigured(f"Required environment variable is missing: {name}")
    return value


SECRET_KEY = required("DJANGO_SECRET_KEY")
FIELD_ENCRYPTION_KEYS = required("FIELD_ENCRYPTION_KEYS").split(",")
try:
    for encryption_key in FIELD_ENCRYPTION_KEYS:
        Fernet(encryption_key.strip().encode())
except (ValueError, TypeError) as exc:
    raise ImproperlyConfigured("FIELD_ENCRYPTION_KEYS must contain valid Fernet keys") from exc
DEBUG = False
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1,backend").split(",")
CSRF_TRUSTED_ORIGINS = os.environ.get("CSRF_TRUSTED_ORIGINS", "http://localhost:3000").split(",")
INSTALLED_APPS = [
    "apps.platform_ops",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "apps.tenants",
    "apps.channels",
    "apps.automations",
    "apps.agents",
    "apps.crm",
    "apps.billing",
    "apps.dashboard_api",
    "apps.analytics",
    "apps.marketplace",
    "apps.content",
    "apps.public_api",
]
MIDDLEWARE = [
    "apps.platform_ops.middleware.ConsoleBoundary",
    "apps.tenants.middleware.PrivateAPIResponses",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
PLATFORM_ADMIN_HOST = os.environ.get("PLATFORM_ADMIN_HOST", "ops.localhost").lower()
PLATFORM_ADMIN_NETWORKS = [
    s.strip() for s in os.environ.get("PLATFORM_ADMIN_NETWORKS", "").split(",") if s.strip()
]
if PLATFORM_ADMIN_HOST not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(PLATFORM_ADMIN_HOST)
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
DATABASES = {"default": dj_database_url.parse(required("DATABASE_URL"), conn_max_age=60)}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "tenants.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 12
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS_URL}
}
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/1")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://redis:6379/2")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_SOFT_TIME_LIMIT = 45
CELERY_TASK_TIME_LIMIT = 60
CELERY_RESULT_EXPIRES = 3600
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 120}
CELERY_BEAT_SCHEDULE = {
    "platform-billing-snapshot": {
        "task": "apps.platform_ops.tasks.sync_subscriptions",
        "schedule": 3600.0,
    },
    "worker-health": {"task": "apps.dashboard_api.tasks.health_check", "schedule": 30.0},
    "flush-audit-outbox": {"task": "apps.tenants.tasks.dispatch_outbox", "schedule": 5.0},
    "expire-auth-tokens": {"task": "apps.tenants.tasks.expire_tokens", "schedule": 86400.0},
}
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {"anon": "60/min", "user": "300/min", "auth": "10/min"},
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
}
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": False,
    "CHECK_REVOKE_TOKEN": True,
}
META_APP_ID = os.environ.get("META_APP_ID", "")
META_APP_SECRET = os.environ.get("META_APP_SECRET", "")
META_REDIRECT_URI = os.environ.get("META_REDIRECT_URI", "http://localhost:3000/api/meta/callback/")
META_SCOPES = os.environ.get(
    "META_SCOPES", "instagram_business_basic,instagram_business_manage_messages"
)
CHANNEL_ADAPTER_MODE = os.environ.get("CHANNEL_ADAPTER_MODE", "disabled")
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [REDIS_URL]},
    }
}
PUBLIC_APP_URL = os.environ.get("PUBLIC_APP_URL", "http://localhost:3000").rstrip("/")
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
SLACK_CLIENT_ID = os.environ.get("SLACK_CLIENT_ID", "")
SLACK_CLIENT_SECRET = os.environ.get("SLACK_CLIENT_SECRET", "")
# Hosted integration sign-in callbacks: <base><provider>/ must be registered with each provider.
INTEGRATION_REDIRECT_BASE = os.environ.get(
    "INTEGRATION_REDIRECT_BASE", PUBLIC_APP_URL + "/api/integrations/callback/"
)
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_METER_EVENT_NAME = os.environ.get("STRIPE_METER_EVENT_NAME", "ai_messages")
import json  # noqa: E402

STRIPE_PRICES = json.loads(os.environ.get("STRIPE_PRICES", "{}"))
PLAN_LIMITS = {
    "starter": {"seats": 3, "channels": 2, "messages": 1000},
    "pro": {"seats": 10, "channels": 5, "messages": 10000},
    "scale": {"seats": 50, "channels": 20, "messages": 100000},
}
RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS", "90"))
# Platform share of paid marketplace templates (destination charges on Connect).
MARKETPLACE_FEE_PERCENT = int(os.environ.get("MARKETPLACE_FEE_PERCENT", "15"))
CELERY_BEAT_SCHEDULE.update(
    {
        "agent-dispatch": {"task": "apps.agents.tasks.dispatch_agents", "schedule": 2.0},
        "integration-dispatch": {"task": "apps.crm.tasks.dispatch_integrations", "schedule": 5.0},
        "integration-refresh": {"task": "apps.crm.tasks.refresh_integrations", "schedule": 300.0},
        "billing-dispatch": {"task": "apps.billing.tasks.dispatch_billing", "schedule": 5.0},
        "data-operations": {
            "task": "apps.tenants.data_tasks.dispatch_data_operations",
            "schedule": 5.0,
        },
        "retention": {"task": "apps.tenants.data_tasks.apply_retention", "schedule": 86400.0},
        "operations-check": {"task": "apps.dashboard_api.tasks.check_backlogs", "schedule": 60.0},
        "marketplace-sellers": {
            "task": "apps.marketplace.tasks.refresh_sellers",
            "schedule": 43200.0,
        },
        "marketplace-purchases": {
            "task": "apps.marketplace.tasks.expire_purchases",
            "schedule": 3600.0,
        },
    }
)
META_API_VERSION = os.environ.get("META_API_VERSION", "v23.0")
# Instagram Login apps and WhatsApp/Messenger apps may be different Meta apps with
# different secrets; each falls back to META_APP_SECRET when a single app is used.
WHATSAPP_APP_SECRET = os.environ.get("WHATSAPP_APP_SECRET", "") or META_APP_SECRET
MESSENGER_APP_SECRET = os.environ.get("MESSENGER_APP_SECRET", "") or META_APP_SECRET
META_WEBHOOK_VERIFY_TOKEN = os.environ.get("META_WEBHOOK_VERIFY_TOKEN", "")
# Outbound budgets are per connected account, so one busy tenant cannot starve others.
# META_APP_CALLS_PER_HOUR optionally adds an app-wide Meta ceiling (0 disables it).
META_CALLS_PER_HOUR = int(os.environ.get("META_CALLS_PER_HOUR", "200"))
CHANNEL_CALLS_PER_HOUR = {
    "instagram": META_CALLS_PER_HOUR,
    "messenger": int(os.environ.get("MESSENGER_CALLS_PER_HOUR", "3600")),
    "whatsapp": int(os.environ.get("WHATSAPP_CALLS_PER_HOUR", "3600")),
    "telegram": int(os.environ.get("TELEGRAM_CALLS_PER_HOUR", "1800")),
}
META_APP_CALLS_PER_HOUR = int(os.environ.get("META_APP_CALLS_PER_HOUR", "0"))
CELERY_BEAT_SCHEDULE.update(
    {
        "channel-dispatch": {"task": "apps.channels.tasks.dispatch_channel_jobs", "schedule": 1.0},
        "channel-refresh": {
            "task": "apps.channels.tasks.refresh_expiring_tokens",
            "schedule": 300.0,
        },
        "automation-dispatch": {"task": "apps.automations.tasks.dispatch_runs", "schedule": 1.0},
        "inbound-dispatch": {"task": "apps.crm.tasks.dispatch_inbound_jobs", "schedule": 5.0},
        "content-dispatch": {
            "task": "apps.content.tasks.dispatch_scheduled_posts",
            "schedule": 30.0,
        },
        "outbound-webhooks": {
            "task": "apps.public_api.tasks.dispatch_outbound_webhooks",
            "schedule": 5.0,
        },
        "experiments": {"task": "apps.analytics.tasks.evaluate_experiments", "schedule": 600.0},
    }
)
DATA_UPLOAD_MAX_MEMORY_SIZE = 3 * 1024 * 1024
PUBLIC_API_RATE = os.environ.get("PUBLIC_API_RATE", "600/min")
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["api_key"] = PUBLIC_API_RATE
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["public"] = "120/min"
from apps.tenants.observability import configure_sentry  # noqa: E402

SENTRY_ENABLED = configure_sentry()
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {"()": "apps.tenants.logging.SafeJSONFormatter"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    # Request paths may contain OAuth authorization codes. Log status via the proxy,
    # never framework URL/error details or provider exception strings.
    "loggers": {
        name: {"handlers": ["console"], "level": "WARNING", "propagate": False}
        for name in ["django.request", "django.server", "httpx", "httpcore"]
    },
}

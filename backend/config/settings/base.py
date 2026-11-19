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


class DynamicAllowedHosts(list):
    """Allowed hosts collection that checks base hosts plus verified custom domains."""

    def __init__(self, base_hosts=()):
        super().__init__([h.strip() for h in base_hosts if h and h.strip()])
        self._cached_domains = set()
        self._last_checked = 0.0

    def append(self, host):
        if not super().__contains__(host):
            super().append(host)

    def extend(self, hosts):
        for h in hosts:
            self.append(h)

    def clear_cache(self):
        self._last_checked = 0.0
        self._cached_domains = set()

    def _get_active_domains(self):
        import os
        import time

        now = time.time()
        is_test = os.environ.get("DJANGO_SETTINGS_MODULE", "").endswith(".test")
        cache_ttl = 0.0 if is_test else 5.0
        if cache_ttl > 0 and (now - self._last_checked < cache_ttl):
            return self._cached_domains
        try:
            from apps.tenants.models import WorkspaceBranding

            domains = set(
                WorkspaceBranding.all_objects.filter(custom_domain_status="active")
                .exclude(custom_domain="")
                .values_list("custom_domain", flat=True)
            )
            self._cached_domains = {d.strip().lower() for d in domains if d.strip()}
            self._last_checked = now
        except Exception:
            pass
        return self._cached_domains

    def __iter__(self):
        yield from super().__iter__()
        yield from self._get_active_domains()

    def __contains__(self, item):
        if not item:
            return False
        clean = item.strip().lower().split(":")[0]
        if super().__contains__(clean):
            return True
        return clean in self._get_active_domains()

    def __len__(self):
        return super().__len__() + len(self._get_active_domains())


ALLOWED_HOSTS = DynamicAllowedHosts(
    os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1,backend").split(",")
)
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
    "apps.tools",
]
MIDDLEWARE = [
    "apps.platform_ops.middleware.ConsoleBoundary",
    "apps.tenants.middleware.PrivateAPIResponses",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.tenants.sessions.IdleSessionMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
PLATFORM_ADMIN_HOST = os.environ.get("PLATFORM_ADMIN_HOST", "ops.localhost").lower()
PLATFORM_ADMIN_NETWORKS = [
    s.strip() for s in os.environ.get("PLATFORM_ADMIN_NETWORKS", "").split(",") if s.strip()
]
# Reverse proxies between the internet and Django. 0 means Django sees the client
# directly; production sits behind the edge proxy in deploy/ and must set at least 1.
# Everything that rate-limits or allow-lists by address reads this through
# apps.tenants.client_ip, and DRF throttles read it as NUM_PROXIES below.
TRUSTED_PROXY_DEPTH = int(os.environ.get("TRUSTED_PROXY_DEPTH", "0"))
# Welcome AI credits, in cents, granted once per workspace when its owner confirms
# their email address. Instantlify pays the provider for these, so the confirmation is what
# keeps the grant from funding throwaway signups. 0 disables it.
SIGNUP_CREDIT_CENTS = int(os.environ.get("SIGNUP_CREDIT_CENTS", "200"))
# How long an unconfirmed signup may hold an email address before it is released.
UNVERIFIED_SIGNUP_DAYS = int(os.environ.get("UNVERIFIED_SIGNUP_DAYS", "14"))
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
SESSION_COOKIE_AGE = 60 * 60
# Polling must not refresh the idle timeout. User interaction renews it explicitly.
SESSION_SAVE_EVERY_REQUEST = False
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
    "meta-data-deletion": {
        "task": "apps.channels.meta_deletion.dispatch_meta_deletions",
        "schedule": 5.0,
    },
    "form-workflows": {
        "task": "apps.tools.form_workflows.dispatch_form_workflows",
        "schedule": 5.0,
    },
    "creator-statistics": {
        "task": "apps.tools.creator_metrics.dispatch_creator_metrics",
        "schedule": 60.0,
    },
    "billing-trial-reminders": {
        "task": "apps.billing.emails.send_trial_reminders",
        "schedule": 86400.0,
    },
    "platform-billing-snapshot": {
        "task": "apps.platform_ops.tasks.sync_subscriptions",
        "schedule": 3600.0,
    },
    "worker-health": {"task": "apps.dashboard_api.tasks.health_check", "schedule": 30.0},
    "uptime-probe": {"task": "apps.platform_ops.uptime.probe_uptime", "schedule": 60.0},
    "flush-audit-outbox": {"task": "apps.tenants.tasks.dispatch_outbox", "schedule": 5.0},
    "expire-auth-tokens": {"task": "apps.tenants.tasks.expire_tokens", "schedule": 86400.0},
    "purge-unverified-signups": {
        "task": "apps.tenants.tasks.purge_unverified_signups",
        "schedule": 86400.0,
    },
}
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "apps.tenants.auth.BanAwareJWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    # Overridable only so the end-to-end stack, where every browser request shares one
    # IP and one fast user, is not throttled; deployments keep these defaults.
    "DEFAULT_THROTTLE_RATES": {
        "anon": os.environ.get("THROTTLE_RATE_ANON", "60/min"),
        "user": os.environ.get("THROTTLE_RATE_USER", "300/min"),
        "auth": os.environ.get("THROTTLE_RATE_AUTH", "10/min"),
        "session_activity": "120/min",
    },
    # Without this DRF keys anonymous throttles on the caller's own X-Forwarded-For
    # header, so a fresh value per request buys an unlimited login/signup/reset rate.
    "NUM_PROXIES": TRUSTED_PROXY_DEPTH,
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
}
# Transactional email (the registry in platform_ops.growth sends through this).
# Without EMAIL_HOST mail goes to the console backend; production refuses that, since
# it would write customer emails, portal links included, into the logs.
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_BACKEND = (
    "django.core.mail.backends.smtp.EmailBackend"
    if EMAIL_HOST
    else "django.core.mail.backends.console.EmailBackend"
)
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "true").lower() != "false"
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "Instantlify <support@instantlify.com>")

# Every password and session check goes through the ban-aware backend, so a banned
# user cannot sign in and an open session of theirs resolves as anonymous.
AUTHENTICATION_BACKENDS = ["apps.tenants.auth.BanAwareBackend"]

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": False,
    "CHECK_REVOKE_TOKEN": True,
}
META_APP_ID = os.environ.get("META_APP_ID", "")
INSTAGRAM_UNIFIED_LOGIN_CONFIG_ID = os.environ.get("INSTAGRAM_UNIFIED_LOGIN_CONFIG_ID", "")
META_APP_SECRET = os.environ.get("META_APP_SECRET", "")
WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID = os.environ.get("WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID", "")
META_REDIRECT_URI = os.environ.get("META_REDIRECT_URI", "http://localhost:3000/api/meta/callback/")
META_SCOPES = os.environ.get(
    "META_SCOPES", "instagram_business_basic,instagram_business_manage_messages"
)
# LinkedIn messaging is not a self-serve API: the adapter posts to /v2/messages, which
# an ordinary app is not granted. Credentials alone therefore do not mean sends will be
# accepted, so the channel stays off until someone confirms this app really was granted
# that access against a real account. Advertising it before then sells a channel that
# accepts a connection and then silently fails to deliver.
LINKEDIN_MESSAGING_APPROVED = os.environ.get("LINKEDIN_MESSAGING_APPROVED", "") == "true"
LINKEDIN_CLIENT_ID = os.environ.get("LINKEDIN_CLIENT_ID", "")
LINKEDIN_CLIENT_SECRET = os.environ.get("LINKEDIN_CLIENT_SECRET", "")
LINKEDIN_REDIRECT_URI = os.environ.get(
    "LINKEDIN_REDIRECT_URI", "http://localhost:3000/api/linkedin/callback/"
)
LINKEDIN_SCOPES = os.environ.get(
    "LINKEDIN_SCOPES", "r_organization_social,w_organization_social,r_messages,w_messages"
)
SNAPCHAT_WEBHOOK_SECRET = os.environ.get("SNAPCHAT_WEBHOOK_SECRET", "")
CHANNEL_ADAPTER_MODE = os.environ.get("CHANNEL_ADAPTER_MODE", "disabled")
ALLOW_TEST_CHANNELS = os.environ.get("ALLOW_TEST_CHANNELS", "false").lower() == "true"
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [REDIS_URL]},
    }
}
PUBLIC_APP_URL = os.environ.get("PUBLIC_APP_URL", "http://localhost:3000").rstrip("/")
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_LOGIN_REDIRECT_URI = os.environ.get("GOOGLE_LOGIN_REDIRECT_URI", "")
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

# Legacy bootstrap only: the plans data migration copies these IDs onto PlanPrice rows.
# Tiers, limits and prices live in the database (billing.Plan) from then on.
STRIPE_PRICES = json.loads(os.environ.get("STRIPE_PRICES", "{}"))
# Plan a workspace is on until it subscribes. "dev" is the unlimited local plan.
DEFAULT_PLAN_SLUG = os.environ.get("DEFAULT_PLAN_SLUG", "free")
# Free trial on a workspace's first subscription, any interval. 0 disables.
STRIPE_TRIAL_DAYS = int(os.environ.get("STRIPE_TRIAL_DAYS", "3"))
# Instantlify's own provider key for workspaces on prepaid credits (2.10).
PLATFORM_OPENAI_API_KEY = os.environ.get("PLATFORM_OPENAI_API_KEY", "")
PLATFORM_AI_MODEL = os.environ.get("PLATFORM_AI_MODEL", "gpt-5")
PLATFORM_ANTHROPIC_API_KEY = os.environ.get("PLATFORM_ANTHROPIC_API_KEY", "")
PLATFORM_GEMINI_API_KEY = os.environ.get("PLATFORM_GEMINI_API_KEY", "")
PLATFORM_GEMINI_MODEL = os.environ.get("PLATFORM_GEMINI_MODEL", "gemini-3.5-flash-lite")
PLATFORM_XAI_API_KEY = os.environ.get("PLATFORM_XAI_API_KEY", "")
PLATFORM_ELEVENLABS_API_KEY = os.environ.get("PLATFORM_ELEVENLABS_API_KEY", "")
PLATFORM_ELEVENLABS_DEFAULT_VOICE_ID = os.environ.get(
    "PLATFORM_ELEVENLABS_DEFAULT_VOICE_ID", "21m00Tcm4TlvDq8ikWAM"
)
# Uptime paging (platform_ops/uptime.py). Each channel is optional.
UPTIME_PROBE_URL = os.environ.get("UPTIME_PROBE_URL", "")
UPTIME_LATENCY_MS = int(os.environ.get("UPTIME_LATENCY_MS", "2500"))
ALERT_WEBHOOK_URL = os.environ.get("ALERT_WEBHOOK_URL", "")
PAGERDUTY_ROUTING_KEY = os.environ.get("PAGERDUTY_ROUTING_KEY", "")
AI_CREDIT_TOPUP_OPTIONS = [1000, 2500, 5000, 10000]
AI_CREDIT_MIN_TOPUP_CENTS = 500
AI_CREDIT_MAX_TOPUP_CENTS = 100000
RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS", "90"))
# Platform share of paid marketplace templates (destination charges on Connect).
MARKETPLACE_FEE_PERCENT = int(os.environ.get("MARKETPLACE_FEE_PERCENT", "15"))
CELERY_BEAT_SCHEDULE.update(
    {
        "agent-dispatch": {"task": "apps.agents.tasks.dispatch_agents", "schedule": 2.0},
        "integration-dispatch": {"task": "apps.crm.tasks.dispatch_integrations", "schedule": 5.0},
        "campaign-dispatch": {"task": "apps.crm.tasks.dispatch_campaigns", "schedule": 5.0},
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
    # Website chat replies are stored for the visitor to poll; no provider is called.
    "webchat": 100000,
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

# Optional platform referral program. Credentials never reach browser responses.
FIRSTPROMOTER_API_KEY = os.environ.get("FIRSTPROMOTER_API_KEY", "")
FIRSTPROMOTER_ACCOUNT_ID = os.environ.get("FIRSTPROMOTER_ACCOUNT_ID", "")
FIRSTPROMOTER_CAMPAIGN_ID = int(os.environ.get("FIRSTPROMOTER_CAMPAIGN_ID", "0") or 0)
FIRSTPROMOTER_CURRENCY = os.environ.get("FIRSTPROMOTER_CURRENCY", "USD").upper()
FIRSTPROMOTER_REVENUE_DIVISOR = os.environ.get("FIRSTPROMOTER_REVENUE_DIVISOR", "100")
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

# Password recovery links expire after one hour.
PASSWORD_RESET_TIMEOUT = 3600

# Confirmed production identity; local PUBLIC_APP_URL remains independently configurable.
APP_DOMAIN = os.environ.get("APP_DOMAIN", "instantlify.com").lower()
CUSTOM_DOMAIN_CNAME_TARGET = os.environ.get("CUSTOM_DOMAIN_CNAME_TARGET", APP_DOMAIN).lower()

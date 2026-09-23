import os

from .base import *  # noqa: F403

DEBUG = True
# Local development never blocks on plan limits (override with DEFAULT_PLAN_SLUG=free).
DEFAULT_PLAN_SLUG = os.environ.get("DEFAULT_PLAN_SLUG", "dev")
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

import os

from .base import *  # noqa: F403

DEBUG = True
# Local development never blocks on plan limits (override with DEFAULT_PLAN_SLUG=free).
DEFAULT_PLAN_SLUG = os.environ.get("DEFAULT_PLAN_SLUG", "dev")
# Inherit base's SMTP backend when EMAIL_HOST is configured; otherwise use console mail.

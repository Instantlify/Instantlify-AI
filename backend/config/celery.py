import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
app = Celery("nemio")
app.config_from_object("django.conf:settings", namespace="CELERY")
# Autodiscovery only imports each app's `tasks` module; task modules with other
# names must be listed here or the worker rejects them as unregistered.
app.autodiscover_tasks()
app.autodiscover_tasks(related_name="data_tasks")

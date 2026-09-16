"""Every scheduled task must be importable by the worker, or Beat fires into the void."""

from django.conf import settings

from config.celery import app


def test_every_beat_entry_is_a_registered_task():
    app.loader.import_default_modules()
    registered = set(app.tasks)
    missing = sorted(
        entry["task"]
        for entry in settings.CELERY_BEAT_SCHEDULE.values()
        if entry["task"] not in registered
    )
    assert missing == []


def test_dispatchers_reference_registered_tasks():
    app.loader.import_default_modules()
    for name in [
        "apps.tenants.data_tasks.process_data_operation",
        "apps.tenants.data_tasks.apply_retention",
        "apps.crm.tasks.transcribe_message",
        "apps.crm.tasks.segment_lead",
        "apps.content.tasks.publish_post",
        "apps.public_api.tasks.deliver_webhook",
        "apps.analytics.tasks.evaluate_experiments",
    ]:
        assert name in app.tasks, name

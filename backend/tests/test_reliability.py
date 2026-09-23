"""Backoff, rate limiting and dispatch behaviour that keeps failures from looping."""

import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
import stripe
from django.apps import apps
from django.conf import settings
from django.db.migrations.loader import MigrationLoader
from django.test import override_settings
from django.utils import timezone
from redis import Redis
from redis.exceptions import RedisError

from apps.agents.models import UsageRecord
from apps.billing import tasks as billing_tasks
from apps.billing.models import BillingEvent
from apps.billing.services import account_for
from apps.channels import tasks as channel_tasks
from apps.channels.models import ChannelConnection, Delivery, WebhookEvent
from apps.tenants.dispatch import enqueue_once

pytestmark = pytest.mark.django_db


def test_every_app_with_models_has_migrations():
    # An app without a migrations package gets no tables from `migrate`, while the test
    # runner still creates them, so the suite would pass against a broken deployment.
    migrated = MigrationLoader(None, ignore_no_migrations=True).migrated_apps
    missing = [
        config.label
        for config in apps.get_app_configs()
        if config.name.startswith("apps.")
        and list(config.get_models())
        and config.label not in migrated
    ]
    assert missing == []


@pytest.fixture
def channel(workspace):
    return ChannelConnection.objects.for_workspace(workspace).create(
        workspace=workspace,
        external_account_id="ig-account",
        display_name="Test",
        access_token="secret",
        expires_at=timezone.now() + timedelta(days=60),
        is_test=True,
    )


def event_for(channel):
    return WebhookEvent.objects.for_workspace(channel.workspace_id).create(
        workspace_id=channel.workspace_id,
        connection=channel,
        event_id="poison",
        payload=json.dumps({"sender_id": "lead", "text": "hi"}),
        available_at=timezone.now(),
    )


def test_poison_webhook_backs_off_then_fails(channel):
    event = event_for(channel)
    with patch("apps.crm.services.receive", side_effect=RuntimeError) as receive:
        channel_tasks.process_webhook(str(channel.workspace_id), str(event.id))
        event.refresh_from_db()
        assert (event.status, event.attempts, event.error_code) == ("pending", 1, "RuntimeError")
        assert event.available_at > timezone.now() + timedelta(seconds=30)
        # Not due yet: redelivery of the task does not re-run the failing work.
        channel_tasks.process_webhook(str(channel.workspace_id), str(event.id))
        assert receive.call_count == 1
        event.attempts = channel_tasks.MAX_WEBHOOK_ATTEMPTS - 1
        event.available_at = timezone.now()
        event.save()
        channel_tasks.process_webhook(str(channel.workspace_id), str(event.id))
    event.refresh_from_db()
    assert event.status == "failed"


def test_failed_webhook_rolls_back_partial_crm_writes(channel):
    from apps.crm.models import Lead

    event = event_for(channel)
    with patch("apps.automations.services.route_message", side_effect=RuntimeError):
        channel_tasks.process_webhook(str(channel.workspace_id), str(event.id))
    assert not Lead.objects.for_workspace(channel.workspace_id).exists()


def test_rate_limited_delivery_waits_for_the_window_without_spending_an_attempt(channel):
    delivery = Delivery.objects.for_workspace(channel.workspace_id).create(
        workspace_id=channel.workspace_id,
        connection=channel,
        recipient_id="lead",
        payload=json.dumps({"text": "hi"}),
        idempotency_key="k",
        available_at=timezone.now(),
    )
    with (
        patch.object(channel_tasks, "rate_limit_wait", return_value=900),
        patch.object(channel_tasks, "adapter_for") as adapter,
    ):
        channel_tasks.send_delivery(str(channel.workspace_id), str(delivery.id))
        adapter.assert_not_called()
    delivery.refresh_from_db()
    assert (delivery.status, delivery.attempts) == ("pending", 0)
    assert delivery.available_at >= timezone.now() + timedelta(seconds=890)


@pytest.fixture
def redis_client():
    client = Redis.from_url(settings.REDIS_URL, socket_timeout=1, socket_connect_timeout=1)
    try:
        client.ping()
    except (RedisError, OSError):
        pytest.skip("Redis is not reachable")
    client.delete(*client.keys("rate:*") or ["rate:none"])
    channel_tasks._redis = client
    yield client
    client.delete(*client.keys("rate:*") or ["rate:none"])
    channel_tasks._redis = None


def live_connection(workspace, account, provider="instagram"):
    return ChannelConnection.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider=provider,
        external_account_id=account,
        display_name=account,
        access_token="t",
        expires_at=timezone.now() + timedelta(days=60),
    )


def test_rate_limit_is_per_account(redis_client, workspace):
    first, second = live_connection(workspace, "a"), live_connection(workspace, "b")
    with override_settings(
        CHANNEL_CALLS_PER_HOUR={**settings.CHANNEL_CALLS_PER_HOUR, "instagram": 2}
    ):
        assert [channel_tasks.rate_limit_wait(first) for _ in range(3)][:2] == [0, 0]
        assert channel_tasks.rate_limit_wait(first) > 0
        # A busy tenant's account does not consume another account's budget.
        assert channel_tasks.rate_limit_wait(second) == 0


def test_app_ceiling_denial_does_not_consume_account_budget(redis_client, workspace):
    first, second = live_connection(workspace, "a"), live_connection(workspace, "b")
    with override_settings(META_APP_CALLS_PER_HOUR=1):
        assert channel_tasks.rate_limit_wait(first) == 0
        assert channel_tasks.rate_limit_wait(second) > 0
    assert int(redis_client.get(f"rate:instagram:{second.pk}") or 0) == 0


def test_enqueue_once_suppresses_duplicate_dispatch():
    task = MagicMock()
    task.name = "example"
    for _ in range(3):
        enqueue_once(task, "w", "p1")
    enqueue_once(task, "w", "p2")
    assert task.delay.call_count == 2


@pytest.fixture
def subscribed(workspace):
    account = account_for(workspace.pk)
    account.customer_id = "cus_1"
    account.subscription_id = "sub_1"
    account.status = "active"
    account.period_start = timezone.now() - timedelta(days=1)
    account.save()
    return account


def usage(workspace, key, **fields):
    return UsageRecord.objects.for_workspace(workspace).create(
        workspace=workspace, key=key, provider="openai", model="m", status="complete", **fields
    )


@override_settings(STRIPE_SECRET_KEY="sk_test_x")
def test_usage_report_backs_off_on_stripe_errors(workspace, subscribed):
    record = usage(workspace, "u1")
    with patch("stripe.billing.MeterEvent.create", side_effect=stripe.APIConnectionError("x")):
        billing_tasks.report_usage(str(workspace.pk), str(record.id))
    record.refresh_from_db()
    assert record.reported_at is None and record.report_attempts == 1
    assert record.report_after > timezone.now()
    assert not billing_tasks.reportable_usage().filter(pk=record.pk).exists()
    record.report_after = timezone.now() - timedelta(seconds=1)
    record.save()
    assert billing_tasks.reportable_usage().filter(pk=record.pk).exists()
    with patch("stripe.billing.MeterEvent.create") as create:
        billing_tasks.report_usage(str(workspace.pk), str(record.id))
        assert create.call_args.kwargs["identifier"] == str(record.id)
    record.refresh_from_db()
    assert record.reported_at is not None


def test_only_subscribed_in_period_generation_usage_is_reportable(workspace, user):
    from apps.tenants.services import create_workspace

    free = create_workspace(user, "Free")
    free_record = usage(free, "free")
    assert not billing_tasks.reportable_usage().filter(pk=free_record.pk).exists()
    account = account_for(workspace.pk)
    account.customer_id, account.subscription_id = "cus_2", "sub_2"
    account.period_start = timezone.now() + timedelta(seconds=5)
    account.save()
    trial = usage(workspace, "trial")
    other_kind = usage(workspace, "seg", kind="segmentation")
    assert not billing_tasks.reportable_usage().filter(pk__in=[trial.pk, other_kind.pk]).exists()


@override_settings(STRIPE_SECRET_KEY="")
def test_billing_dispatch_skips_usage_without_stripe(workspace, subscribed):
    usage(workspace, "u2")
    with patch.object(billing_tasks.report_usage, "delay") as delay:
        billing_tasks.dispatch_billing()
        delay.assert_not_called()


def test_malformed_billing_event_fails_instead_of_looping(workspace):
    account_for(workspace.pk)
    event = BillingEvent.objects.for_workspace(workspace).create(
        workspace=workspace, event_id="evt_bad", payload=json.dumps({"type": "x"})
    )
    billing_tasks.process_event(str(workspace.pk), str(event.id))
    event.refresh_from_db()
    assert event.status == "failed"


def test_billing_event_updates_plan_limits(workspace):
    from tests.conftest import price_for

    price_for("starter", stripe_price_id="price_base")
    account_for(workspace.pk)
    now = int(timezone.now().timestamp())
    payload = {
        "type": "customer.subscription.updated",
        "created": now,
        "data": {
            "object": {
                "id": "sub_9",
                "status": "active",
                "items": {"data": [{"price": {"id": "price_base"}, "current_period_start": now}]},
            }
        },
    }
    event = BillingEvent.objects.for_workspace(workspace).create(
        workspace=workspace, event_id="evt_ok", payload=json.dumps(payload)
    )
    billing_tasks.process_event(str(workspace.pk), str(event.id))
    event.refresh_from_db()
    account = account_for(workspace.pk)
    assert event.status == "processed"
    assert (account.plan, account.seat_limit, account.status) == ("starter", 3, "active")


def test_data_operation_failure_is_terminal(workspace):
    from apps.tenants.data_tasks import process_data_operation
    from apps.tenants.models import DataOperation

    job = DataOperation.objects.for_workspace(workspace).create(workspace=workspace, kind="export")
    with patch("apps.tenants.data_tasks.run_data_operation", side_effect=RuntimeError):
        process_data_operation(str(workspace.pk), str(job.id))
    job.refresh_from_db()
    assert (job.status, job.error_code) == ("failed", "RuntimeError")

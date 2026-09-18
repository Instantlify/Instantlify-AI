"""The console dashboard (2.5.1): every figure comes from data, never a literal."""

import time
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.test import Client
from django.utils import timezone

from apps.platform_ops.metrics import PlatformMetricsService
from apps.platform_ops.models import PlatformRole
from apps.platform_ops.security import new_secret

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def setup(settings):
    settings.ALLOWED_HOSTS = [*settings.ALLOWED_HOSTS, "ops.localhost"]
    cache.clear()


@pytest.fixture
def operator(user):
    user.is_staff = True
    user.save()
    return PlatformRole.objects.create(
        user=user, role="owner", otp_secret=new_secret(), otp_confirmed=True
    )


def console(operator):
    client = Client(HTTP_HOST="ops.localhost")
    client.force_login(operator.user)
    session = client.session
    session["platform_password_at"] = time.time()
    session["platform_mfa"] = {"version": operator.version, "until": time.time() + 1800}
    session.save()
    return client


def test_mrr_and_trial_pipeline_are_computed_from_accounts(workspace, user):
    from apps.billing.services import account_for
    from apps.tenants.services import create_workspace
    from tests.conftest import price_for

    paying = account_for(workspace.pk)
    paying.plan_price = price_for("pro", "monthly")
    paying.status = "active"
    paying.save()
    trial = account_for(create_workspace(user, "Second").pk)
    trial.plan_price = price_for("pro", "annual")
    trial.status = "trialing"
    trial.save()

    metrics = PlatformMetricsService().snapshot()
    assert metrics["mrr"]["paying"] == 1
    assert metrics["mrr"]["value"] == Decimal(paying.plan_price.price_cents) / 100
    assert "no Stripe snapshot" in metrics["mrr"]["basis"]
    # An annual trial is valued at its monthly equivalent, and labelled as pipeline.
    [row] = metrics["trial_mrr"]
    assert row["count"] == 1
    assert row["total"] == (Decimal(trial.plan_price.price_cents) / 12 / 100).quantize(
        Decimal("0.01")
    )


def test_billing_locks_and_bans_are_counted(workspace, user):
    from apps.billing.services import account_for
    from tests.conftest import price_for

    account = account_for(workspace.pk)
    account.plan_price = price_for("pro", "monthly")
    account.status = "past_due"
    account.save()
    user.is_banned = True
    user.save()
    metrics = PlatformMetricsService().snapshot()
    assert metrics["locks"]["count"] == 1
    assert metrics["locks"]["owed"] == Decimal(account.plan_price.price_cents) / 100
    assert metrics["users"]["banned"] == 1


def test_stripe_revenue_is_unknown_not_zero_without_stripe(settings):
    """Zero would read as "no revenue"; with Stripe unconfigured the honest answer is
    that the figure is unavailable."""
    settings.STRIPE_SECRET_KEY = ""
    assert PlatformMetricsService(source="stripe").revenue()["value"] is None


def test_database_revenue_counts_paid_invoices_and_credit_purchases(workspace):
    import json

    from apps.billing.models import AICreditTransaction, BillingEvent

    BillingEvent.objects.for_workspace(workspace).create(
        workspace=workspace,
        event_id="evt_paid",
        payload=json.dumps({"type": "invoice.paid", "data": {"object": {"amount_paid": 2500}}}),
    )
    BillingEvent.objects.for_workspace(workspace).create(
        workspace=workspace,
        event_id="evt_failed",
        payload=json.dumps(
            {"type": "invoice.payment_failed", "data": {"object": {"amount_paid": 9900}}}
        ),
    )
    AICreditTransaction.objects.for_workspace(workspace).create(
        workspace=workspace,
        key="t1",
        type="topup",
        amount_cents=Decimal("1000"),
        remaining_balance_cents=Decimal("1000"),
    )
    assert PlatformMetricsService().revenue()["value"] == Decimal("35.00")


def test_expensive_figures_are_cached_between_renders(workspace):
    from apps.crm.models import Lead

    first = PlatformMetricsService().messages()
    with patch("apps.crm.models.Message.all_objects") as manager:
        second = PlatformMetricsService().messages()
    manager.filter.assert_not_called()
    assert second == first
    # Cheap counts stay live: a new lead shows up immediately.
    Lead.objects.for_workspace(workspace).create(workspace=workspace, name="New")
    assert PlatformMetricsService().contacts()["total"] == 1


def test_unknown_source_and_window_fall_back_safely():
    metrics = PlatformMetricsService(source="nonsense", days=13)
    assert metrics.source == "database" and metrics.days == 30


def test_overview_renders_no_screenshot_figures(operator):
    """The overview once showed fixed BooSend numbers. None of them may come back."""
    client = console(operator)
    with patch("redis.Redis.get", return_value=None), patch("redis.Redis.ttl", return_value=-2):
        body = client.get("/ops/?tab=overview").content.decode()
    for literal in ["5,403", "$4,469.00", "237,394,058", "13,289,478", "61,342,864", "$10,026.68"]:
        assert literal not in body, literal
    assert "Claude MCP connected" in body and "No MCP connector" not in body
    stripe_view = client.get("/ops/?tab=overview&source=stripe&days=7").content.decode()
    assert "Stripe not configured" in stripe_view


def test_active_users_means_signed_in_within_the_window(user):
    user.last_login = timezone.now() - timedelta(days=40)
    user.save()
    assert PlatformMetricsService(days=30).users()["active"] == 0
    assert PlatformMetricsService(days=90).users()["active"] == 1


def test_charts_are_computed_from_data(workspace, user):
    import json

    from apps.billing.models import BillingEvent
    from apps.billing.services import account_for
    from apps.platform_ops.models import SubscriptionSnapshot
    from apps.tenants.models import User
    from tests.conftest import price_for

    User.objects.filter(pk=user.pk).update(date_joined=timezone.now() - timedelta(days=2))
    now = int(time.time())
    for event_id, kind in [("evt_a", "created"), ("evt_b", "created"), ("evt_c", "deleted")]:
        BillingEvent.objects.for_workspace(workspace).create(
            workspace=workspace,
            event_id=event_id,
            payload=json.dumps({"type": f"customer.subscription.{kind}", "created": now}),
        )
    account = account_for(workspace.pk)
    account.plan_price = price_for("pro", "monthly")
    account.status = "active"
    account.save()
    SubscriptionSnapshot.objects.create(
        workspace=workspace,
        day=timezone.now().date(),
        currency="usd",
        monthly_cents=Decimal("4900"),
        status="active",
    )

    charts = PlatformMetricsService(days=30).snapshot()["charts"]
    assert charts["unit"] == "day"
    assert charts["signups"]["total"] == 1 and not charts["signups"]["empty"]
    assert isinstance(charts["signups"]["total"], int)  # renders "1 total", not "1.0"
    assert charts["subscriptions"]["totals"] == [2, 1]
    [tier] = charts["tiers"]["segments"]
    assert (tier["count"], tier["percent"]) == (1, "100%")
    assert charts["mrr"]["dots"][-1]["title"].endswith("$49.00")


def test_charts_show_empty_states_rather_than_invented_series(operator):
    charts = PlatformMetricsService(days=365).charts()
    assert charts["unit"] == "month"
    assert charts["subscriptions"]["empty"] and charts["mrr"]["empty"]
    client = console(operator)
    with patch("redis.Redis.get", return_value=None), patch("redis.Redis.ttl", return_value=-2):
        body = client.get("/ops/?tab=overview&days=365").content.decode()
    assert "No MRR history yet" in body and "No subscription changes" in body
    # The old mockup's fixed tooltip, legend and axis may never render again.
    for literal in ["Signups: 7", "Rh_architect", "$1200", "Last 30 Days ▾"]:
        assert literal not in body, literal


def test_chart_geometry():
    from datetime import date

    from apps.platform_ops import charts

    assert charts.nice_ceiling(7) == (8, 2)
    assert charts.nice_ceiling(130) == (200, 50)
    assert charts.buckets(date(2026, 1, 30), date(2026, 3, 2), "month") == [
        date(2026, 1, 1),
        date(2026, 2, 1),
        date(2026, 3, 1),
    ]
    line = charts.line_chart([("a", 0), ("b", 4), ("c", 8)])
    assert [dot["y"] for dot in line["dots"]] == [charts.BOTTOM, 90.0, charts.TOP]
    ring = charts.donut([(str(n), 1) for n in range(10)])
    assert len(ring["segments"]) == 8 and ring["segments"][-1]["name"] == "Other"
    assert ring["segments"][-1]["count"] == 3


def test_support_badge_counts_unread_tickets(operator):
    from apps.platform_ops.models import SupportTicket

    client = console(operator)
    with patch("redis.Redis.get", return_value=None), patch("redis.Redis.ttl", return_value=-2):
        assert 'class="nav-badge"' not in client.get("/ops/?tab=team").content.decode()
        SupportTicket.objects.create(subject="Help", reporter_email="a@example.com")
        body = client.get("/ops/?tab=team").content.decode()
    assert 'title="Unread tickets">1</span>' in body


def test_purge_e2e_accounts_removes_only_browser_test_data(settings, user):
    from django.core.management import CommandError, call_command

    from apps.tenants.models import User, Workspace
    from apps.tenants.services import create_workspace

    bot = User.objects.create_user(
        username="e2e-1", email="e2e-1789@example.com", password="A-very-long-pass42"
    )
    solo = create_workspace(bot, "E2E Studio")
    shared = create_workspace(bot, "Shared")
    shared.membership_set.create(workspace=shared, user=user, role="agent")
    settings.CHANNEL_ADAPTER_MODE = "disabled"
    with pytest.raises(CommandError):
        call_command("purge_e2e_accounts")
    settings.CHANNEL_ADAPTER_MODE = "fake"
    call_command("purge_e2e_accounts")
    assert not User.objects.filter(pk=bot.pk).exists()
    assert not Workspace.objects.filter(pk=solo.pk).exists()
    # A real person belongs to this one, so it stays.
    assert (
        Workspace.objects.filter(pk=shared.pk).exists() and User.objects.filter(pk=user.pk).exists()
    )

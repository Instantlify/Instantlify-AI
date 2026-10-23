"""Gate placement, downgrade soft-lock, trial checkout, public catalog and the Tiers tab."""

import json
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.agents.models import AgentConfig, AgentRun, ToolCall
from apps.agents.tasks import process_run
from apps.agents.tools import propose
from apps.billing import tasks as billing_tasks
from apps.billing.models import BillingJob, Plan, PlanPrice
from apps.billing.services import account_for
from apps.channels.models import ChannelConnection
from apps.content.models import ScheduledPost
from apps.content.tasks import publish_post
from apps.crm.models import IntegrationConfig, IntegrationJob
from apps.crm.services import receive
from apps.crm.tasks import process_integration
from apps.tenants.models import AuditEvent
from tests.conftest import price_for, set_limits
from tests.test_platform_ops import console_host, operator, signed_client  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def quiet_notify():
    with patch("apps.crm.services.notify"), patch("apps.crm.tasks.notify"):
        yield


def connection(workspace, account_id="ig-1"):
    return ChannelConnection.objects.for_workspace(workspace).create(
        workspace=workspace,
        external_account_id=account_id,
        display_name=account_id,
        access_token="secret",
        expires_at=timezone.now() + timedelta(days=60),
        is_test=True,
    )


def agent_run(workspace, channel, text="hello"):
    from apps.channels.models import WebhookEvent

    event = WebhookEvent.objects.for_workspace(workspace).create(
        workspace=workspace,
        connection=channel,
        event_id=f"evt-{WebhookEvent.all_objects.count()}",
        payload="{}",
        available_at=timezone.now(),
    )
    message = receive(event, {"sender_id": "lead-1", "text": text})
    message.conversation.ai_enabled = True
    message.conversation.save()
    run, _ = AgentRun.objects.for_workspace(workspace).get_or_create(
        message=message, defaults={"workspace_id": workspace.pk}
    )
    return run


# --- agent


def test_agent_config_and_runs_are_gated(client, workspace):
    url = f"/api/workspaces/{workspace.pk}/agent/"
    assert client.put(url, {"name": "Bot", "is_test": True}, format="json").status_code in {
        200,
        201,
    }
    channel = connection(workspace)
    AgentConfig.objects.for_workspace(workspace).update(enabled=True)
    set_limits(workspace, ai_agent_enabled=False)
    response = client.put(url, {"name": "Bot"}, format="json")
    assert response.status_code == 402 and response.json()["upgrade_required"] == "ai_agent_enabled"
    run = agent_run(workspace, channel)
    with patch("apps.agents.runtime.provider_for") as provider:
        process_run(str(workspace.pk), str(run.id))
        provider.assert_not_called()
    run.refresh_from_db()
    assert (run.status, run.error_code) == ("skipped", "plan_limit")
    assert (
        AuditEvent.objects.for_workspace(workspace)
        .filter(action="plan.blocked:ai_agent_enabled")
        .exists()
    )


def test_voice_tool_is_refused_without_the_feature(workspace):
    channel = connection(workspace)
    config = AgentConfig.objects.for_workspace(workspace).create(
        workspace=workspace, enabled=True, is_test=True, allowed_tools=["send_voice_note"]
    )
    run = agent_run(workspace, channel)
    set_limits(workspace, voice_notes_enabled=False)
    with pytest.raises(ValueError, match="plan_voice_notes"):
        propose(run, "send_voice_note", {"text": "hi"}, config)
    rejected = ToolCall.objects.for_workspace(workspace).get()
    assert rejected.status == "rejected" and "plan_voice_notes" in rejected.output


# --- integrations


def test_integration_connect_and_jobs_are_gated(client, workspace):
    set_limits(workspace, integrations_unlocked=False)
    base = f"/api/workspaces/{workspace.pk}/integrations/"
    saved = client.post(base, {"provider": "slack", "is_test": True}, format="json")
    assert saved.status_code == 402 and saved.json()["upgrade_required"] == "integrations_unlocked"
    assert client.post(base + "slack/oauth/").status_code == 402
    slack = IntegrationConfig.objects.for_workspace(workspace).create(
        workspace=workspace, provider="slack", is_test=True
    )
    job = IntegrationJob.objects.for_workspace(workspace).create(
        workspace=workspace,
        integration=slack,
        operation="notify",
        payload=json.dumps({"text": "hi"}),
        idempotency_key="j1",
        available_at=timezone.now(),
    )
    process_integration(str(workspace.pk), str(job.id))
    job.refresh_from_db()
    assert (job.status, json.loads(job.result)) == ("needs_review", {"error": "plan_limit"})


# --- content and the downgrade soft-lock


def test_content_scheduling_is_gated(client, workspace):
    channel = connection(workspace)
    set_limits(workspace, content_scheduling_enabled=False)
    response = client.post(
        f"/api/workspaces/{workspace.pk}/posts/",
        {
            "connection": channel.pk,
            "media_url": "https://cdn.example.com/x.jpg",
            "scheduled_at": (timezone.now() + timedelta(hours=1)).isoformat(),
        },
        format="json",
    )
    assert response.status_code == 402
    assert response.json()["upgrade_required"] == "content_scheduling_enabled"


def test_downgrade_soft_locks_the_newest_connections(client, workspace):
    set_limits(workspace, max_instagram_accounts=3)
    older, newer = connection(workspace, "ig-old"), connection(workspace, "ig-new")
    # Same-instant inserts would tie on created_at; the older one is unambiguous here.
    ChannelConnection.all_objects.filter(pk=older.pk).update(
        created_at=timezone.now() - timedelta(days=1)
    )
    set_limits(workspace, max_instagram_accounts=1)  # downgrade while over the cap
    listed = {
        c["display_name"]: c["locked"]
        for c in client.get(f"/api/workspaces/{workspace.pk}/connections/").json()["results"]
    }
    assert listed == {"ig-old": False, "ig-new": True}
    posts = f"/api/workspaces/{workspace.pk}/posts/"
    body = {
        "media_url": "https://cdn.example.com/x.jpg",
        "scheduled_at": (timezone.now() + timedelta(hours=1)).isoformat(),
    }
    blocked = client.post(posts, {**body, "connection": newer.pk}, format="json")
    assert blocked.status_code == 402
    assert blocked.json()["upgrade_required"] == "max_instagram_accounts"
    assert "still receives and replies" in blocked.json()["detail"]
    assert client.post(posts, {**body, "connection": older.pk}, format="json").status_code == 201
    assert (
        client.post(
            f"/api/workspaces/{workspace.pk}/channels/{newer.pk}/simulate/",
            {"text": "hi"},
            format="json",
        ).status_code
        == 402
    )
    assert (
        client.post(
            f"/api/workspaces/{workspace.pk}/channels/{older.pk}/simulate/",
            {"text": "hi"},
            format="json",
        ).status_code
        == 202
    )
    # A post already queued on the locked account is failed at publish time, not silently dropped.
    queued = ScheduledPost.objects.for_workspace(workspace).create(
        workspace=workspace,
        connection=newer,
        media_url="https://cdn.example.com/y.jpg",
        scheduled_at=timezone.now(),
    )
    publish_post(str(workspace.pk), str(queued.id))
    queued.refresh_from_db()
    assert (queued.status, queued.error_code) == ("failed", "plan_limit")
    # Disconnecting the extra account is always allowed and clears the lock.
    assert (
        client.post(f"/api/workspaces/{workspace.pk}/channels/{newer.pk}/disconnect/").status_code
        == 200
    )
    assert (
        client.post(
            f"/api/workspaces/{workspace.pk}/channels/{older.pk}/simulate/",
            {"text": "hi"},
            format="json",
        ).status_code
        == 202
    )


# --- trial and public catalog


def test_first_checkout_carries_the_trial(workspace, settings):
    settings.STRIPE_SECRET_KEY = "sk_test_x"
    price_for("starter", stripe_price_id="price_starter")
    account = account_for(workspace.pk)
    account.customer_id = "cus_1"
    account.save()

    def run_job(key):
        job = BillingJob.objects.for_workspace(workspace).create(
            workspace=workspace,
            kind="checkout",
            plan="starter",
            interval="monthly",
            request_key=key,
        )
        with patch("stripe.checkout.Session.create") as create:
            create.return_value.url = "https://checkout.stripe.com/x"
            billing_tasks.process_job(str(workspace.pk), str(job.id))
        return create.call_args.kwargs["subscription_data"]

    assert run_job("first")["trial_period_days"] == 7
    account.subscription_id, account.status = "sub_old", "canceled"  # a re-subscribe
    account.save()
    assert "trial_period_days" not in run_job("again")


def test_public_catalog_is_anonymous_and_excludes_custom_tiers():
    body = APIClient().get("/api/public/plans/").json()
    assert [plan["slug"] for plan in body["plans"]] == ["free", "starter", "pro", "scale"]
    assert body["trial_days"] == 7
    pro = next(plan for plan in body["plans"] if plan["slug"] == "pro")
    assert pro["is_featured"] and {p["interval"] for p in pro["prices"]} == {"monthly", "annual"}


# --- console Tiers tab (2.5.7)


def tier_form(**overrides):
    return {
        "name": "RocketHub lifetime",
        "partner_label": "RocketHub",
        "sort_order": "10",
        "monthly_price_cents": "0",
        "annual_price_cents": "29900",
        "max_instagram_accounts": "3",
        "max_contacts": "",
        "team_seats": "2",
        "max_ai_messages": "500",
        "ai_agent_enabled": "on",
        "integrations_unlocked": "on",
        "is_active": "on",
        "annual_stripe_price_id": "price_rh_year",
        **overrides,
    }


def test_owner_creates_edits_and_deletes_custom_tiers(operator, workspace):  # noqa: F811
    client = signed_client(operator)
    with patch("redis.Redis.get", return_value=None), patch("redis.Redis.ttl", return_value=-2):
        page = client.get("/ops/?tab=tiers&interval=annual")
    assert page.status_code == 200 and b"Create custom tier" in page.content
    assert page.context["interval"] == "annual"
    assert client.post("/ops/tiers/", {"slug": "rockethub", **tier_form()}).status_code == 302
    plan = Plan.objects.get(slug="rockethub")
    assert (plan.is_custom, plan.partner_label, plan.name) == (
        True,
        "RocketHub",
        "RocketHub lifetime",
    )
    limits = plan.limits
    assert (limits.max_instagram_accounts, limits.max_contacts, limits.team_seats) == (3, None, 2)
    assert (limits.ai_agent_enabled, limits.content_scheduling_enabled) == (True, False)
    annual = PlanPrice.objects.get(plan=plan, billing_interval="annual")
    assert (annual.price_cents, annual.stripe_price_id) == (29900, "price_rh_year")
    assert (
        client.post("/ops/tiers/", {"slug": "rockethub", **tier_form()}).status_code == 403
    )  # duplicate
    client.post(
        f"/ops/tiers/{plan.pk}/", tier_form(name="RocketHub v2", team_seats="", is_active="")
    )
    plan.refresh_from_db()
    assert (plan.name, plan.is_active, plan.limits.team_seats) == ("RocketHub v2", False, None)
    # Subscribers protect a tier from deletion.
    account = account_for(workspace.pk)
    account.plan_price = annual
    account.save()
    assert client.post(f"/ops/tiers/{plan.pk}/", {"action": "delete"}).status_code == 403
    account.plan_price = None
    account.save()
    assert client.post(f"/ops/tiers/{plan.pk}/", {"action": "delete"}).status_code == 302
    assert not Plan.objects.filter(slug="rockethub").exists()


def test_default_tiers_only_accept_stripe_wiring(operator):  # noqa: F811
    client = signed_client(operator)
    pro = Plan.objects.get(slug="pro")
    response = client.post(
        f"/ops/tiers/{pro.pk}/",
        tier_form(
            name="Hacked",
            team_seats="999",
            monthly_price_cents="1",
            monthly_stripe_price_id="price_pro_m",
        ),
    )
    assert response.status_code == 302
    pro.refresh_from_db()
    assert (pro.name, pro.limits.team_seats, pro.is_custom) == ("Pro", 10, False)
    monthly = PlanPrice.objects.get(plan=pro, billing_interval="monthly")
    assert (monthly.price_cents, monthly.stripe_price_id) == (2500, "price_pro_m")
    assert client.post(f"/ops/tiers/{pro.pk}/", {"action": "delete"}).status_code == 403
    assert Plan.objects.filter(slug="pro").exists()


def test_support_staff_cannot_touch_tiers(operator):  # noqa: F811
    operator.role = "support"
    operator.save()
    client = signed_client(operator)
    assert client.post("/ops/tiers/", {"slug": "x", **tier_form()}).status_code == 403
    assert not Plan.objects.filter(slug="x").exists()

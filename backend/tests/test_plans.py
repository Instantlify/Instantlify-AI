"""Plan model, seed data and the single plan gate."""

import json
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.views import APIView

from apps.billing import tasks as billing_tasks
from apps.billing.gating import (
    PlanLimitExceeded,
    check_feature,
    check_within_limit,
    guard,
    require_feature,
    require_within_limit,
)
from apps.billing.models import BillingEvent, BillingJob, Plan, PlanLimits, PlanPrice
from apps.billing.services import account_for
from apps.tenants.models import AuditEvent
from tests.conftest import price_for, set_limits

pytestmark = pytest.mark.django_db


def test_seed_creates_public_tiers_prices_and_a_dev_plan():
    tiers = {plan.slug: plan for plan in Plan.objects.all()}
    assert list(tiers) == ["free", "starter", "pro", "scale", "dev"]
    assert tiers["pro"].is_featured and not tiers["starter"].is_featured
    assert tiers["dev"].is_custom and not tiers["dev"].is_active
    prices = {
        (p.plan.slug, p.billing_interval): p.price_cents
        for p in PlanPrice.objects.select_related("plan")
    }
    assert prices == {
        ("starter", "monthly"): 1200,
        ("starter", "annual"): 13000,
        ("pro", "monthly"): 2500,
        ("pro", "annual"): 24000,
        ("scale", "monthly"): 5000,
        ("scale", "annual"): 42000,
    }
    free, scale, dev = tiers["free"].limits, tiers["scale"].limits, tiers["dev"].limits
    assert (free.team_seats, free.max_instagram_accounts, free.max_ai_messages) == (1, 1, 100)
    assert (scale.team_seats, scale.max_instagram_accounts, scale.max_ai_messages) == (
        50,
        20,
        100000,
    )
    assert dev.as_dict() == {
        **{name: None for name in PlanLimits.NUMERIC},
        **{name: True for name in PlanLimits.FLAGS},
    }


def test_new_workspace_is_on_the_default_plan(workspace, settings):
    account = account_for(workspace.pk)
    assert account.plan_price is None
    assert (account.plan, account.seat_limit, account.usage_limit) == ("free", 1, 100)
    settings.DEFAULT_PLAN_SLUG = "dev"
    assert (account.plan, account.seat_limit, account.usage_limit) == ("dev", None, None)


def test_feature_and_limit_checks_raise_a_402_with_the_limit_name(workspace):
    set_limits(workspace, ai_agent_enabled=False, max_contacts=0, team_seats=None)
    with pytest.raises(PlanLimitExceeded) as blocked:
        check_feature(workspace.pk, "ai_agent_enabled")
    assert blocked.value.status_code == 402
    assert blocked.value.detail["upgrade_required"] == "ai_agent_enabled"
    assert blocked.value.detail["code"] == "plan_limit_exceeded"
    with pytest.raises(PlanLimitExceeded):
        check_within_limit(workspace.pk, "max_contacts")
    check_within_limit(workspace.pk, "team_seats", adding=500)  # None = unlimited
    check_feature(workspace.pk, "integrations_unlocked")
    with pytest.raises(ValueError):
        check_feature(workspace.pk, "not_a_feature")


def test_view_decorators_gate_after_membership(workspace, user):
    class View(APIView):
        @require_feature("voice_notes_enabled")
        def post(self, request, workspace_id):
            return Response({"ok": True})

        @require_within_limit("max_instagram_accounts")
        def put(self, request, workspace_id):
            return Response({"ok": True})

    factory = APIRequestFactory()

    def call(method, who, wid=str(workspace.pk)):
        request = getattr(factory, method)("/x/")
        force_authenticate(request, who)
        return View.as_view()(request, workspace_id=wid)

    assert call("post", user).status_code == 200
    set_limits(workspace, voice_notes_enabled=False, max_instagram_accounts=0)
    response = call("post", user)
    assert response.status_code == 402
    assert response.data == {
        "detail": "Voice notes are not included in your plan.",
        "code": "plan_limit_exceeded",
        "upgrade_required": "voice_notes_enabled",
    }
    assert call("put", user).status_code == 402
    from apps.tenants.models import User

    stranger = User.objects.create_user(username="s", email="s@example.com")
    assert call("post", stranger).status_code == 404  # plan state is not disclosed


def test_task_guard_fails_cleanly_and_tells_the_workspace(workspace):
    assert guard(workspace.pk, "ai_agent_enabled") is True
    set_limits(workspace, ai_agent_enabled=False)
    with patch("apps.crm.services.notify") as notify:
        assert guard(workspace.pk, "ai_agent_enabled") is False
        notify.assert_called_once_with(workspace.pk)
    assert (
        AuditEvent.objects.for_workspace(workspace)
        .filter(action="plan.blocked:ai_agent_enabled")
        .exists()
    )


def test_seat_and_channel_gates_use_the_plan(client, workspace):
    set_limits(workspace, team_seats=1, max_instagram_accounts=0)
    invite = client.post(
        f"/api/workspaces/{workspace.pk}/invitations/",
        {"email": "new@example.com", "role": "agent"},
        format="json",
    )
    assert invite.status_code == 402 and invite.json()["upgrade_required"] == "team_seats"
    started = client.post(f"/api/workspaces/{workspace.pk}/meta/connect/")
    assert started.status_code == 402
    assert started.json()["upgrade_required"] == "max_instagram_accounts"
    connect = client.post(
        f"/api/workspaces/{workspace.pk}/channels/connect/",
        {"provider": "telegram", "external_account_id": "1", "display_name": "B", "is_test": True},
        format="json",
    )
    assert connect.status_code == 402


def test_billing_view_exposes_limits_and_catalog(client, workspace):
    body = client.get(f"/api/workspaces/{workspace.pk}/billing/").json()
    assert body["plan"] == "free" and body["limits"]["team_seats"] == 1
    assert [plan["slug"] for plan in body["catalog"]] == ["free", "starter", "pro", "scale"]
    pro = next(plan for plan in body["catalog"] if plan["slug"] == "pro")
    assert pro["is_featured"] and pro["limits"]["max_ai_messages"] == 10000
    assert {p["interval"]: p["price_cents"] for p in pro["prices"]} == {
        "monthly": 2500,
        "annual": 24000,
    }
    assert set(body["plans"]) == {"starter", "pro", "scale"}


def test_checkout_uses_the_plan_price_for_the_chosen_interval(client, workspace, settings):
    settings.STRIPE_SECRET_KEY = "sk_test_x"
    url = f"/api/workspaces/{workspace.pk}/billing/"
    bad = client.post(
        url, {"kind": "checkout", "plan": "dev"}, format="json", HTTP_IDEMPOTENCY_KEY="k0"
    )
    assert bad.status_code == 400  # inactive plans cannot be bought
    response = client.post(
        url,
        {"kind": "checkout", "plan": "pro", "interval": "annual"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="k1",
    )
    assert response.status_code == 202
    job = BillingJob.objects.for_workspace(workspace).get(request_key="k1")
    assert (job.plan, job.interval) == ("pro", "annual")
    account = account_for(workspace.pk)
    account.customer_id = "cus_1"
    account.save()
    billing_tasks.process_job(str(workspace.pk), str(job.id))
    job.refresh_from_db()
    assert json.loads(job.result) == {"error": "billing_provider_error"}  # no Stripe price yet
    job.status = "pending"
    job.save()
    price = price_for("pro", "annual", stripe_price_id="price_pro_year")
    price.stripe_meter_price_id = "price_meter"
    price.save()
    with patch("stripe.checkout.Session.create") as create:
        create.return_value.url = "https://checkout.stripe.com/x"
        billing_tasks.process_job(str(workspace.pk), str(job.id))
    kwargs = create.call_args.kwargs
    assert kwargs["line_items"] == [
        {"price": "price_pro_year", "quantity": 1},
        {"price": "price_meter"},
    ]
    assert kwargs["subscription_data"]["metadata"]["interval"] == "annual"


def test_a_plan_chosen_during_onboarding_returns_to_the_wizard(client, workspace, settings):
    settings.STRIPE_SECRET_KEY = "sk_test_x"
    settings.PUBLIC_APP_URL = "https://app.example.com"
    price_for("pro", "monthly", stripe_price_id="price_pro_month")
    account = account_for(workspace.pk)
    account.customer_id = "cus_1"
    account.save()
    client.post(
        f"/api/workspaces/{workspace.pk}/billing/",
        {"kind": "checkout", "plan": "pro", "interval": "monthly", "return_to": "onboarding"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="ob1",
    )
    job = BillingJob.objects.for_workspace(workspace).get(request_key="ob1")
    with patch("stripe.checkout.Session.create") as create:
        create.return_value.url = "https://checkout.stripe.com/x"
        billing_tasks.process_job(str(workspace.pk), str(job.id))
    kwargs = create.call_args.kwargs
    assert kwargs["success_url"] == "https://app.example.com/onboarding/?billing=success"
    assert kwargs["cancel_url"] == "https://app.example.com/onboarding/?billing=cancelled"


def test_upgrading_a_live_subscription_opens_the_stripe_plan_change(client, workspace, settings):
    """A second Checkout would bill twice: a subscriber picks a plan and Stripe's portal
    opens on the confirm step for that exact switch."""
    settings.STRIPE_SECRET_KEY = "sk_test_x"
    price = price_for("scale", "monthly", stripe_price_id="price_scale_month")
    price.stripe_meter_price_id = "price_scale_meter"
    price.save()
    account = account_for(workspace.pk)
    account.customer_id, account.subscription_id, account.status = "cus_1", "sub_1", "active"
    account.save()
    client.post(
        f"/api/workspaces/{workspace.pk}/billing/",
        {"kind": "checkout", "plan": "scale", "interval": "monthly"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="up1",
    )
    job = BillingJob.objects.for_workspace(workspace).get(request_key="up1")
    subscription = {
        "items": {
            "data": [
                {"id": "si_base", "price": {"id": "price_pro_month", "recurring": {}}},
                {
                    "id": "si_meter",
                    "price": {"id": "price_pro_meter", "recurring": {"usage_type": "metered"}},
                },
            ]
        }
    }
    with (
        patch("stripe.Subscription.retrieve", return_value=subscription),
        patch("stripe.billing_portal.Session.create") as portal,
        patch("stripe.checkout.Session.create") as checkout,
    ):
        portal.return_value.url = "https://billing.stripe.com/p/x"
        billing_tasks.process_job(str(workspace.pk), str(job.id))
    job.refresh_from_db()
    assert json.loads(job.result) == {"url": "https://billing.stripe.com/p/x"}
    checkout.assert_not_called()
    flow = portal.call_args.kwargs["flow_data"]
    assert flow["type"] == "subscription_update_confirm"
    assert flow["subscription_update_confirm"]["items"] == [
        {"id": "si_base", "price": "price_scale_month", "quantity": 1},
        {"id": "si_meter", "price": "price_scale_meter"},
    ]
    assert "settings?tab=subscription" in portal.call_args.kwargs["return_url"]


def test_subscription_webhook_maps_price_to_plan_and_interval(workspace):
    price_for("scale", "annual", stripe_price_id="price_scale_year")
    account = account_for(workspace.pk)
    account.customer_id = "cus_1"
    account.save()
    payload = {
        "type": "customer.subscription.created",
        "created": int(timezone.now().timestamp()),
        "data": {
            "object": {
                "id": "sub_1",
                "status": "active",
                "items": {
                    "data": [
                        {
                            "price": {
                                "id": "price_scale_year",
                                "recurring": {"interval": "year", "interval_count": 1},
                            }
                        }
                    ]
                },
            }
        },
    }
    event = BillingEvent.objects.for_workspace(workspace).create(
        workspace=workspace, event_id="evt_1", payload=json.dumps(payload)
    )
    billing_tasks.process_event(str(workspace.pk), str(event.id))
    account = account_for(workspace.pk)
    assert account.plan_price.plan.slug == "scale"
    assert (account.plan, account.billing_interval, account.seat_limit) == ("scale", "annual", 50)
    assert account.limits.max_ai_messages == 100000


def test_a_tier_with_subscribers_cannot_be_deleted(workspace):
    from django.db.models import ProtectedError

    plan = set_limits(workspace)
    with pytest.raises(ProtectedError):
        plan.delete()


def test_stripe_returns_land_in_the_workspace_not_on_the_marketing_page(workspace, settings):
    """PUBLIC_APP_URL is the anonymous marketing page: it offers "Sign in" and "Get
    started" whatever the session says, so someone who just paid reads it as having been
    signed out. Every Stripe return has to come back to their own Subscription tab."""
    from apps.billing.services import payments_url

    settings.PUBLIC_APP_URL = "https://app.example.com"
    url = payments_url(workspace.pk, "?billing=success")
    base = f"https://app.example.com/w/{workspace.pk}/settings?tab=subscription"
    assert url == f"{base}&billing=success"
    assert payments_url(workspace.pk) == base


def test_no_stripe_return_points_at_the_bare_app_url():
    """A regression guard: these are easy to write as PUBLIC_APP_URL + "?x=y" and the
    mistake is invisible until someone pays."""
    import re
    from pathlib import Path

    billing = Path(__file__).resolve().parent.parent / "apps" / "billing"
    offenders = []
    for source in billing.glob("*.py"):
        for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"(success_url|cancel_url|return_url)\s*=\s*.*PUBLIC_APP_URL", line):
                offenders.append(f"{source.name}:{number}")
    assert not offenders, f"Use payments_url() instead of PUBLIC_APP_URL at: {offenders}"

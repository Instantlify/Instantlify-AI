"""Exercise real SDK objects and signature parsing, without provider network calls."""

import hashlib
import hmac
import json
import time
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import stripe
from django.test import Client
from django.utils import timezone

from apps.billing.emails import billing_line
from apps.billing.models import BillingEvent
from apps.billing.services import account_for
from apps.billing.tasks import apply_event, plan_change_session, reconcile_account
from apps.crm.models import IntegrationConfig
from apps.platform_ops.models import SubscriptionSnapshot
from apps.platform_ops.tasks import sync_subscriptions
from tests.conftest import price_for

pytestmark = pytest.mark.django_db
TEST_SECRET = "whsec_isolated_unit_test_only"


def signed_post(path, event, *, secret=TEST_SECRET):
    payload = json.dumps(event)
    timestamp = int(time.time())
    digest = hmac.new(
        secret.encode(), f"{timestamp}.{payload}".encode(), hashlib.sha256
    ).hexdigest()
    return Client().post(
        path,
        payload,
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=f"t={timestamp},v1={digest}",
    )


def subscription(*, status="trialing"):
    return stripe.Subscription.construct_from(
        {
            "object": "subscription",
            "id": "sub_sdk",
            "customer": "cus_sdk",
            "status": status,
            "trial_end": 1_900_000_000 if status == "trialing" else None,
            "items": {
                "object": "list",
                "data": [
                    {
                        "object": "subscription_item",
                        "id": "si_sdk",
                        "current_period_start": 1_800_000_000,
                        "current_period_end": 1_900_000_000,
                        "price": {
                            "object": "price",
                            "id": "price_sdk",
                            "currency": "usd",
                            "unit_amount": 2900,
                            "recurring": {"interval": "month", "usage_type": "licensed"},
                        },
                    }
                ],
            },
        },
        "sk_test_unit_only",
    )


def test_real_signature_parser_routes_nested_sdk_objects_and_deduplicates(workspace, settings):
    settings.STRIPE_WEBHOOK_SECRET = TEST_SECRET
    account = account_for(workspace.pk)
    account.customer_id = "cus_sdk"
    account.save()
    event = {
        "object": "event",
        "id": "evt_sdk",
        "type": "customer.subscription.created",
        "created": int(time.time()),
        "data": {"object": subscription().to_dict()},
    }
    assert signed_post("/webhooks/stripe/", event, secret="wrong").status_code == 400
    assert not BillingEvent.objects.for_workspace(workspace).exists()
    assert signed_post("/webhooks/stripe/", event).status_code == 200
    assert signed_post("/webhooks/stripe/", event).status_code == 200
    assert BillingEvent.objects.for_workspace(workspace).filter(event_id="evt_sdk").count() == 1


def test_tenant_callback_reads_real_sdk_checkout_object(workspace):
    IntegrationConfig.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider="stripe",
        credentials=json.dumps({"webhook_secret": TEST_SECRET}),
        is_test=False,
    )
    event = {
        "object": "event",
        "id": "evt_checkout_sdk",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "object": "checkout.session",
                "id": "cs_sdk",
                "payment_status": "paid",
                "amount_total": 2900,
            }
        },
    }
    with patch("apps.billing.payments.mark_paid") as mark:
        assert signed_post(f"/webhooks/stripe/{workspace.pk}/", event).status_code == 200
    mark.assert_called_once_with(workspace.pk, "cs_sdk", 2900)


def test_sdk_subscription_reconciliation_and_revenue_sync(workspace, settings):
    settings.STRIPE_SECRET_KEY = "sk_test_unit_only"
    price_for("starter", stripe_price_id="price_sdk")
    account = account_for(workspace.pk)
    account.subscription_id, account.status = "sub_sdk", "active"
    account.save()
    assert reconcile_account(workspace.pk, subscription()) is True
    account.refresh_from_db()
    assert account.status == "trialing"
    assert account.plan == "starter"
    assert account.period_end and account.trial_ends_at
    with patch("stripe.Subscription.retrieve", return_value=subscription(status="active")):
        sync_subscriptions()
    account.refresh_from_db()
    assert account.status == "active"
    assert SubscriptionSnapshot.objects.get(workspace=workspace).monthly_cents == 2900


def test_plan_change_reads_nested_sdk_prices(workspace, settings):
    settings.STRIPE_SECRET_KEY = "sk_test_unit_only"
    account = account_for(workspace.pk)
    account.subscription_id, account.customer_id = "sub_sdk", "cus_sdk"
    target = price_for("pro", stripe_price_id="price_target")
    job = SimpleNamespace(id="job_sdk", return_to="", workspace_id=workspace.pk)
    with (
        patch("stripe.Subscription.retrieve", return_value=subscription()),
        patch("stripe.billing_portal.Session.create") as portal,
    ):
        plan_change_session(workspace.pk, account, target, job)
    assert portal.call_args.kwargs["flow_data"]["subscription_update_confirm"]["items"] == [
        {"id": "si_sdk", "price": "price_target", "quantity": 1}
    ]


def test_billing_email_reads_real_sdk_invoice_preview(workspace, settings):
    settings.STRIPE_SECRET_KEY = "sk_test_unit_only"
    account = account_for(workspace.pk)
    account.status, account.customer_id, account.subscription_id = "active", "cus_sdk", "sub_sdk"
    preview = stripe.Invoice.construct_from(
        {"amount_due": 2900, "currency": "usd", "period_end": 1_900_000_000}, "sk_test_unit_only"
    )
    with patch("stripe.Invoice.create_preview", return_value=preview):
        assert "29.00 USD" in billing_line(account)


@pytest.mark.parametrize("reason", ["subscription_create", "subscription_update"])
def test_paid_zero_invoice_does_not_end_ongoing_trial(workspace, reason):
    account = account_for(workspace.pk)
    account.subscription_id, account.status = "sub_sdk", "trialing"
    account.trial_ends_at = timezone.now() + timedelta(days=7)
    account.save()
    result = apply_event(
        workspace.pk,
        {
            "type": "invoice.paid",
            "created": int(time.time()),
            "data": {
                "object": {
                    "subscription": "sub_sdk",
                    "billing_reason": reason,
                    "amount_due": 0,
                }
            },
        },
        "evt_trial_invoice",
    )
    account.refresh_from_db()
    assert result == "ignored"
    assert account.status == "trialing"


def test_zero_invoice_after_trial_end_can_activate_subscription(workspace):
    account = account_for(workspace.pk)
    account.subscription_id, account.status = "sub_sdk", "trialing"
    account.trial_ends_at = timezone.now() - timedelta(seconds=1)
    account.save()
    assert (
        apply_event(
            workspace.pk,
            {
                "type": "invoice.paid",
                "created": int(time.time()),
                "data": {"object": {"subscription": "sub_sdk", "amount_due": 0}},
            },
            "evt_trial_ended_invoice",
        )
        == "processed"
    )
    account.refresh_from_db()
    assert account.status == "active"

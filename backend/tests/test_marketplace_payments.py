"""Paid marketplace templates: Connect onboarding, checkout, webhook fulfilment, sync."""

import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import stripe
from django.utils import timezone
from rest_framework.test import APIClient

from apps.automations.models import Automation
from apps.automations.services import publish
from apps.billing.models import BillingEvent
from apps.billing.tasks import process_event
from apps.billing.views import event_workspace
from apps.marketplace import services
from apps.marketplace.models import SellerAccount, Template, TemplatePurchase
from apps.marketplace.tasks import expire_purchases, refresh_sellers
from apps.platform_ops.models import Control
from apps.tenants.models import AuditEvent, User
from apps.tenants.services import create_workspace

pytestmark = pytest.mark.django_db


def automation(workspace, user, text):
    item = Automation.objects.for_workspace(workspace).create(workspace=workspace, name=text)
    return publish(
        item,
        {
            "start": "hi",
            "triggers": [{"kind": "comment", "keyword": "price"}],
            "nodes": [
                {"id": "hi", "data": {"kind": "send_message", "text": text}},
                {"id": "end", "data": {"kind": "end"}},
            ],
            "edges": [{"source": "hi", "target": "end"}],
        },
        user,
    )


def account(status="active", entries=()):
    """Shape of a v2 Account with a recipient configuration."""
    return SimpleNamespace(
        id="acct_seller",
        configuration=SimpleNamespace(
            recipient=SimpleNamespace(
                capabilities=SimpleNamespace(
                    stripe_balance=SimpleNamespace(stripe_transfers=SimpleNamespace(status=status))
                )
            )
        ),
        requirements=SimpleNamespace(entries=list(entries)),
    )


@pytest.fixture
def stripe_client(settings):
    settings.STRIPE_SECRET_KEY = "sk_test_x"
    client = MagicMock()
    client.v2.core.accounts.create.return_value = account("pending", ["identity.name"])
    client.v2.core.accounts.retrieve.return_value = account("active")
    client.v2.core.account_links.create.return_value = SimpleNamespace(
        url="https://connect.stripe.com/setup/x"
    )
    client.accounts.login_links.create.return_value = SimpleNamespace(
        url="https://connect.stripe.com/express/x"
    )
    client.checkout.sessions.create.return_value = SimpleNamespace(
        id="cs_test_1", url="https://checkout.stripe.com/c/cs_test_1"
    )
    with patch("apps.marketplace.services.StripeClient", return_value=client):
        yield client


@pytest.fixture
def buyer():
    stranger = User.objects.create_user(username="buyer", email="buyer@example.com")
    workspace = create_workspace(stranger, "Buyer Co")
    client = APIClient()
    client.force_authenticate(stranger)
    return SimpleNamespace(user=stranger, workspace=workspace, client=client)


def onboard(client, workspace, stripe_client):
    response = client.post(f"/api/workspaces/{workspace.pk}/templates/payouts/", {}, format="json")
    assert response.status_code == 202, response.content
    assert response.json()["url"].startswith("https://connect.stripe.com/")
    refreshed = client.post(
        f"/api/workspaces/{workspace.pk}/templates/payouts/", {"action": "refresh"}, format="json"
    )
    assert refreshed.status_code == 200
    return refreshed.json()


def publish_paid(client, workspace, user, price=1900):
    item = automation(workspace, user, "Premium!")
    response = client.post(
        f"/api/workspaces/{workspace.pk}/templates/publish/",
        {"automation": item.pk, "title": "Premium", "price_cents": price},
        format="json",
    )
    return response


def test_paid_publishing_requires_connected_payouts(client, workspace, user, stripe_client):
    assert publish_paid(client, workspace, user).status_code == 400
    assert publish_paid(client, workspace, user, price=50).status_code == 400  # below $1
    status = onboard(client, workspace, stripe_client)
    assert status == {
        "connected": True,
        "transfers_status": "active",
        "requirements_due": False,
        "can_sell": True,
        "checked_at": status["checked_at"],
        "country": "us",
    }
    created = stripe_client.v2.core.accounts.create.call_args
    assert created.args[0]["dashboard"] == "express"
    assert created.args[0]["defaults"]["responsibilities"] == {
        "fees_collector": "application",
        "losses_collector": "application",
    }
    assert created.args[0]["configuration"]["recipient"]["capabilities"]["stripe_balance"] == {
        "stripe_transfers": {"requested": True}
    }
    assert created.kwargs == {} and created.args[1]["idempotency_key"].startswith("nemio-seller:")
    assert publish_paid(client, workspace, user).status_code == 201
    assert SellerAccount.objects.for_workspace(workspace).count() == 1
    # A second onboarding call reuses the same account.
    client.post(f"/api/workspaces/{workspace.pk}/templates/payouts/", {}, format="json")
    assert stripe_client.v2.core.accounts.create.call_count == 1
    assert SellerAccount.objects.for_workspace(workspace).count() == 1


def test_payouts_endpoints_are_owner_only_and_never_expose_the_account(
    client, workspace, user, stripe_client
):
    onboard(client, workspace, stripe_client)
    admin = User.objects.create_user(username="admin", email="admin@example.com")
    from apps.tenants.models import Membership

    Membership.objects.for_workspace(workspace).create(
        workspace=workspace, user=admin, role="admin"
    )
    theirs = APIClient()
    theirs.force_authenticate(admin)
    status = theirs.get(f"/api/workspaces/{workspace.pk}/templates/payouts/")
    assert status.status_code == 200 and "acct_" not in status.content.decode()
    assert (
        theirs.post(
            f"/api/workspaces/{workspace.pk}/templates/payouts/",
            {"action": "dashboard"},
            format="json",
        ).status_code
        == 403
    )
    dashboard = client.post(
        f"/api/workspaces/{workspace.pk}/templates/payouts/", {"action": "dashboard"}, format="json"
    )
    assert dashboard.json()["url"].startswith("https://connect.stripe.com/express/")
    bad = client.post(
        f"/api/workspaces/{workspace.pk}/templates/payouts/", {"country": "usa"}, format="json"
    )
    assert bad.status_code == 400


def test_paid_install_creates_a_destination_charge_and_installs_on_webhook(
    client, workspace, user, stripe_client, buyer, settings
):
    settings.MARKETPLACE_FEE_PERCENT = 15
    onboard(client, workspace, stripe_client)
    slug = publish_paid(client, workspace, user).json()["slug"]
    template = Template.all_objects.get(slug=slug)

    started = buyer.client.post(
        f"/api/workspaces/{buyer.workspace.pk}/templates/install/",
        {"slug": slug, "idempotency_key": "k1"},
        format="json",
    )
    assert started.status_code == 202, started.content
    body = started.json()
    assert body["status"] == "pending"
    assert body["checkout_url"] == "https://checkout.stripe.com/c/cs_test_1"
    params = stripe_client.checkout.sessions.create.call_args.args[0]
    assert params["mode"] == "payment"
    assert params["line_items"][0]["price_data"]["unit_amount"] == 1900
    assert params["payment_intent_data"]["application_fee_amount"] == 285
    assert params["payment_intent_data"]["transfer_data"] == {"destination": "acct_seller"}
    assert params["metadata"]["nemio_template_purchase"] == body["purchase_id"]
    assert params["metadata"]["workspace"] == str(buyer.workspace.pk)
    assert "payment_method_types" not in params
    # Same key: same purchase, no second session.
    again = buyer.client.post(
        f"/api/workspaces/{buyer.workspace.pk}/templates/install/",
        {"slug": slug, "idempotency_key": "k1"},
        format="json",
    )
    assert again.json()["purchase_id"] == body["purchase_id"]
    assert stripe_client.checkout.sessions.create.call_count == 1
    assert not Automation.objects.for_workspace(buyer.workspace).exists()

    # Stripe confirms payment through the platform webhook; nothing is trusted from the client.
    event = {
        "id": "evt_1",
        "type": "checkout.session.completed",
        "created": 1_800_000_000,
        "data": {
            "object": {
                "id": "cs_test_1",
                "payment_status": "paid",
                "amount_total": 1900,
                "metadata": params["metadata"],
            }
        },
    }
    assert event_workspace(event) == buyer.workspace.pk
    with patch("stripe.Webhook.construct_event", return_value=event):
        settings.STRIPE_WEBHOOK_SECRET = "whsec_x"
        response = APIClient().post(
            "/webhooks/stripe/", data=json.dumps(event), content_type="application/json"
        )
    assert response.status_code == 200
    stored = BillingEvent.objects.for_workspace(buyer.workspace).get(event_id="evt_1")
    process_event(str(buyer.workspace.pk), str(stored.pk))
    stored.refresh_from_db()
    assert stored.status == "processed"
    purchase = TemplatePurchase.objects.for_workspace(buyer.workspace).get()
    assert purchase.status == "installed" and purchase.paid_at
    copy = Automation.objects.for_workspace(buyer.workspace).get()
    assert purchase.automation_id == copy.pk and copy.installed_from == template.pk
    assert Template.all_objects.get(pk=template.pk).install_count == 1
    assert list(
        AuditEvent.objects.for_workspace(buyer.workspace)
        .filter(action__startswith="template.")
        .order_by("created_at")
        .values_list("action", flat=True)
    ) == ["template.purchase_started", "template.purchase_paid", "template.installed"]
    # Replayed webhook: idempotent.
    process_event(str(buyer.workspace.pk), str(stored.pk))
    assert Automation.objects.for_workspace(buyer.workspace).count() == 1

    # Already paid: a later install (new key) is free and does not charge again.
    reinstall = buyer.client.post(
        f"/api/workspaces/{buyer.workspace.pk}/templates/install/",
        {"slug": slug, "idempotency_key": "k2"},
        format="json",
    )
    assert reinstall.status_code == 201
    assert reinstall.json()["automation_id"] == str(copy.pk)
    assert stripe_client.checkout.sessions.create.call_count == 1
    listing = buyer.client.get(f"/api/workspaces/{buyer.workspace.pk}/templates/purchases/")
    assert [p["status"] for p in listing.json()["results"]] == ["installed"]


def test_webhook_ignores_forged_purchase_metadata(workspace, buyer):
    purchase = TemplatePurchase.objects.for_workspace(buyer.workspace).create(
        workspace=buyer.workspace,
        template_id=workspace.pk,
        seller_workspace_id=workspace.pk,
        title="x",
        amount_cents=100,
        idempotency_key="k",
        checkout_session_id="cs_1",
    )
    forged = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_1",
                "metadata": {
                    "nemio_template_purchase": str(purchase.pk),
                    "workspace": str(workspace.pk),
                },
            }
        },
    }
    assert event_workspace(forged) is None
    forged["data"]["object"]["metadata"]["nemio_template_purchase"] = "not-a-uuid"
    assert event_workspace(forged) is None
    assert event_workspace({"type": "checkout.session.completed", "data": {"object": {}}}) is None


def test_sync_fallback_and_expiry(client, workspace, user, stripe_client, buyer):
    onboard(client, workspace, stripe_client)
    slug = publish_paid(client, workspace, user).json()["slug"]
    started = buyer.client.post(
        f"/api/workspaces/{buyer.workspace.pk}/templates/install/",
        {"slug": slug, "idempotency_key": "k1"},
        format="json",
    ).json()
    url = f"/api/workspaces/{buyer.workspace.pk}/templates/purchases/{started['purchase_id']}/"
    stripe_client.checkout.sessions.retrieve.return_value = SimpleNamespace(
        id="cs_test_1", payment_status="unpaid", status="open", amount_total=1900
    )
    assert buyer.client.post(url, {}, format="json").json()["status"] == "pending"
    stripe_client.checkout.sessions.retrieve.return_value = SimpleNamespace(
        id="cs_test_1", payment_status="paid", status="complete", amount_total=1900
    )
    synced = buyer.client.post(url, {}, format="json").json()
    assert synced["status"] == "installed" and synced["automation_id"]
    # The author cannot read the buyer's purchase.
    assert client.get(url).status_code in {403, 404}

    stale = TemplatePurchase.objects.for_workspace(buyer.workspace).create(
        workspace=buyer.workspace,
        template_id=Template.all_objects.get(slug=slug).pk,
        seller_workspace_id=workspace.pk,
        title="Premium",
        amount_cents=1900,
        idempotency_key="old",
        checkout_session_id="cs_old",
    )
    TemplatePurchase.all_objects.filter(pk=stale.pk).update(
        created_at=timezone.now() - timedelta(hours=26)
    )
    expire_purchases()
    stale.refresh_from_db()
    assert stale.status == "expired"


def test_restricted_or_paused_sellers_cannot_be_purchased(
    client, workspace, user, stripe_client, buyer
):
    onboard(client, workspace, stripe_client)
    slug = publish_paid(client, workspace, user).json()["slug"]
    seller = SellerAccount.objects.for_workspace(workspace).get()
    # A stale capability is re-read before checkout; Stripe now reports restricted.
    SellerAccount.all_objects.filter(pk=seller.pk).update(
        checked_at=timezone.now() - timedelta(hours=2)
    )
    stripe_client.v2.core.accounts.retrieve.return_value = account(
        "restricted", ["identity.verification"]
    )
    blocked = buyer.client.post(
        f"/api/workspaces/{buyer.workspace.pk}/templates/install/",
        {"slug": slug, "idempotency_key": "k1"},
        format="json",
    )
    assert blocked.status_code == 400 and "payouts" in blocked.content.decode()
    seller.refresh_from_db()
    assert seller.transfers_status == "restricted" and seller.requirements_due
    assert not stripe_client.checkout.sessions.create.called
    assert not TemplatePurchase.objects.for_workspace(buyer.workspace).exists()

    # The periodic refresh recovers the account once Stripe reports active again.
    stripe_client.v2.core.accounts.retrieve.return_value = account("active")
    SellerAccount.all_objects.filter(pk=seller.pk).update(
        checked_at=timezone.now() - timedelta(hours=13)
    )
    refresh_sellers()
    seller.refresh_from_db()
    assert seller.transfers_status == "active"

    Control.objects.create(scope="", key="marketplace", reason="incident")
    paused = buyer.client.post(
        f"/api/workspaces/{buyer.workspace.pk}/templates/install/",
        {"slug": slug, "idempotency_key": "k2"},
        format="json",
    )
    assert paused.status_code == 400 and "paused" in paused.content.decode()
    assert not stripe_client.checkout.sessions.create.called


def test_provider_errors_do_not_leave_half_made_purchases(
    client, workspace, user, stripe_client, buyer
):
    onboard(client, workspace, stripe_client)
    slug = publish_paid(client, workspace, user).json()["slug"]
    stripe_client.checkout.sessions.create.side_effect = stripe.APIError("down")
    response = buyer.client.post(
        f"/api/workspaces/{buyer.workspace.pk}/templates/install/",
        {"slug": slug, "idempotency_key": "k1"},
        format="json",
    )
    assert response.status_code == 400
    assert not TemplatePurchase.objects.for_workspace(buyer.workspace).exists()


def test_free_and_own_templates_still_install_directly(client, workspace, user, stripe_client):
    onboard(client, workspace, stripe_client)
    slug = publish_paid(client, workspace, user).json()["slug"]
    # The author installing their own paid template is not charged.
    mine = client.post(
        f"/api/workspaces/{workspace.pk}/templates/install/", {"slug": slug}, format="json"
    )
    assert mine.status_code == 201
    assert not stripe_client.checkout.sessions.create.called


def test_fee_rounds_up_and_is_capped():
    from django.test import override_settings

    with override_settings(MARKETPLACE_FEE_PERCENT=15):
        assert services.fee_for(1900) == 285
        assert services.fee_for(1) == 1
        assert services.fee_for(101) == 16
    with override_settings(MARKETPLACE_FEE_PERCENT=250):
        assert services.fee_for(500) == 500


def test_without_stripe_configured_paid_installs_fail_cleanly(
    client, workspace, user, buyer, settings
):
    settings.STRIPE_SECRET_KEY = ""
    SellerAccount.objects.for_workspace(workspace).create(
        workspace=workspace,
        stripe_account_id="acct_x",
        transfers_status="active",
        requirements_due=False,
        checked_at=timezone.now(),
    )
    slug = publish_paid(client, workspace, user).json()["slug"]
    response = buyer.client.post(
        f"/api/workspaces/{buyer.workspace.pk}/templates/install/",
        {"slug": slug, "idempotency_key": "k1"},
        format="json",
    )
    assert response.status_code == 400 and "not configured" in response.content.decode()
    assert (
        client.post(
            f"/api/workspaces/{workspace.pk}/templates/payouts/", {}, format="json"
        ).status_code
        == 400
    )

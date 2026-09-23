"""Money and email loops: promo redemption, plan-change and portal emails, reminders."""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.core import mail
from django.core.cache import cache
from django.utils import timezone

from apps.billing import emails
from apps.billing.services import account_for
from apps.platform_ops import growth
from apps.platform_ops.models import PromoCampaign, PromoCampaignEvent
from tests.conftest import price_for

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clean(settings):
    cache.clear()
    mail.outbox.clear()
    settings.STRIPE_SECRET_KEY = "sk_test_fake"


def claimed(workspace, user, **fields):
    campaign = PromoCampaign.objects.create(
        slug="launch", discount_percent=30, is_live=True, **fields
    )
    growth.record_campaign_event(campaign, "claimed", workspace=workspace, user=user)
    return campaign


def test_a_claimed_campaign_becomes_a_coupon_at_checkout(workspace, user):
    claimed(workspace, user)
    with patch("stripe.Coupon.retrieve"), patch("stripe.Coupon.create") as create:
        promotion = growth.coupon_for_checkout(workspace.pk, price_for("pro", "monthly"))
    assert promotion == {"slug": "launch", "coupon": "nemio-promo-launch-30"}
    create.assert_not_called()


def test_no_coupon_without_a_claim_or_for_the_wrong_interval(workspace, user):
    assert growth.coupon_for_checkout(workspace.pk, price_for("pro", "monthly")) is None
    claimed(workspace, user, target_interval="annual")
    with patch("stripe.Coupon.retrieve"):
        assert growth.coupon_for_checkout(workspace.pk, price_for("pro", "monthly")) is None


def test_a_stripe_error_means_full_price_not_a_failed_checkout(workspace, user):
    import stripe

    claimed(workspace, user)
    with patch("stripe.Coupon.retrieve", side_effect=stripe.APIConnectionError("down")):
        assert growth.coupon_for_checkout(workspace.pk, price_for("pro", "monthly")) is None


def test_redemption_is_recorded_once_per_subscription(workspace, user):
    campaign = claimed(workspace, user)
    growth.record_redemption("launch", workspace.pk, "sub_123")
    growth.record_redemption("launch", workspace.pk, "sub_123")
    assert growth.campaign_totals(campaign) == {"shown": 0, "claimed": 1, "redeemed": 1}
    # Once redeemed, the same workspace is not offered the coupon again.
    with patch("stripe.Coupon.retrieve"):
        assert growth.coupon_for_checkout(workspace.pk, price_for("pro", "monthly")) is None


def test_subscription_webhook_with_a_discount_records_the_redemption(workspace, user):
    from apps.billing.tasks import apply_event

    claimed(workspace, user)
    account = account_for(workspace.pk)
    subscription = {
        "id": "sub_9",
        "status": "active",
        "metadata": {"promo_campaign": "launch"},
        "discounts": ["di_1"],
        "items": {"data": []},
        "customer": account.customer_id or "cus_1",
    }
    apply_event(
        workspace.pk,
        {"type": "customer.subscription.created", "created": 10, "data": {"object": subscription}},
        "evt_1",
    )
    assert PromoCampaignEvent.objects.filter(event_type="redeemed", reference="sub_9").exists()


def test_plan_changed_email_uses_the_live_invoice_preview(workspace, user):
    account = account_for(workspace.pk)
    account.plan_price = price_for("pro", "monthly")
    account.status = "active"
    account.customer_id = "cus_1"
    account.subscription_id = "sub_1"
    account.save()
    preview = {"amount_due": 2500, "currency": "usd", "next_payment_attempt": 1_800_000_000}
    with patch("stripe.Invoice.create_preview", return_value=preview) as live:
        assert emails.send_plan_changed(str(workspace.pk)) == 1
    live.assert_called_once()
    assert "25.00 USD" in mail.outbox[-1].body


def test_portal_link_is_created_at_send_time(workspace, user):
    account = account_for(workspace.pk)
    account.customer_id = "cus_2"
    account.save()
    member = emails.owners(workspace.pk)[0]
    session = MagicMock(url="https://billing.stripe.com/p/session_abc")
    with patch("stripe.billing_portal.Session.create", return_value=session) as create:
        assert emails.send_manage_link(account, member)
    create.assert_called_once()
    assert "session_abc" in mail.outbox[-1].body


def test_trial_reminder_goes_once_to_trials_ending_in_the_window(workspace, user):
    from apps.tenants.services import create_workspace

    ending = account_for(workspace.pk)
    ending.status = "trialing"
    ending.plan_price = price_for("pro", "monthly")
    ending.trial_ends_at = timezone.now() + timedelta(days=2, hours=12)
    ending.save()
    later = account_for(create_workspace(user, "Later").pk)
    later.status = "trialing"
    later.trial_ends_at = timezone.now() + timedelta(days=6)
    later.save()
    mail.outbox.clear()
    assert emails.send_trial_reminders() == 1
    assert emails.send_trial_reminders() == 0
    assert "trial" in mail.outbox[-1].subject.lower()


def test_credits_low_is_sent_at_most_once_a_day(workspace):
    assert emails.credits_low(workspace.pk, Decimal("0")) == 1
    assert emails.credits_low(workspace.pk, Decimal("0")) == 0
    assert "credits" in mail.outbox[-1].subject.lower()

"""Phase 1/4/5 hardening: send-time policy, integration OAuth lifecycle, billing
reconciliation and the data lifecycle."""

import json
import secrets
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.billing import tasks as billing_tasks
from apps.billing.models import BillingEvent, Offer, Payment
from apps.billing.services import account_for
from apps.channels.models import ChannelConnection, Delivery, OAuthState, WebhookEvent
from apps.channels.tasks import send_delivery
from apps.channels.transport import ProviderError, RetryableError
from apps.crm.models import IntegrationConfig, IntegrationJob, Message
from apps.crm.services import queue_reply, receive
from apps.tenants.models import AuditEvent, DataOperation, User

pytestmark = pytest.mark.django_db


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


def inbound(channel, sender="lead-1", **payload):
    event = WebhookEvent.objects.for_workspace(channel.workspace_id).create(
        workspace_id=channel.workspace_id,
        connection=channel,
        event_id="evt-" + secrets.token_hex(4),
        payload="{}",
        available_at=timezone.now(),
    )
    with patch("apps.crm.services.notify"):
        return receive(event, {"sender_id": sender, "text": "hi", **payload})


def dispatch(item):
    Delivery.all_objects.filter(pk=item.pk).update(available_at=timezone.now())
    send_delivery(str(item.workspace_id), str(item.id))
    item.refresh_from_db()
    return item


# --- Phase 1: policy is re-evaluated when the message is actually sent


def test_send_time_recheck_fails_opted_out_and_closed_window(channel):
    message = inbound(channel)
    conversation = message.conversation
    with patch("apps.crm.services.notify"):
        first = queue_reply(conversation, "hello", "k1")
        second = queue_reply(conversation, "again", "k2")
    lead = conversation.identity.lead
    lead.opted_out = True
    lead.save()
    assert (dispatch(first).status, first.error_code) == ("failed", "opted_out")
    lead.opted_out = False
    lead.save()
    conversation.last_inbound_at = timezone.now() - timedelta(hours=25)
    conversation.save()
    assert (dispatch(second).status, second.error_code) == ("failed", "messaging_window_closed")
    assert (
        AuditEvent.objects.for_workspace(channel.workspace_id)
        .filter(action="delivery.failed")
        .count()
        == 2
    )


def test_one_private_reply_per_comment(channel):
    message = inbound(channel, kind="comment", comment_id="c1")
    conversation = message.conversation
    with patch("apps.crm.services.notify"):
        first = queue_reply(conversation, "psst", "p1", private_reply_id="c1")
        with pytest.raises(ValidationError):
            queue_reply(conversation, "too early", "early", private_reply_id="c1")
        inbound(channel, kind="dm")
        second = queue_reply(conversation, "more", "p2", private_reply_id="c1")
    assert first.recipient_id == "c1"
    # After a private response, the spent allowance continues in the DM thread.
    assert second.recipient_id == conversation.identity.external_id
    assert dispatch(first).status == "sent"
    # A sibling that bypassed queue_reply is stopped at send time.
    third = Delivery.objects.for_workspace(channel.workspace_id).create(
        workspace_id=channel.workspace_id,
        connection=channel,
        recipient_id="c1",
        idempotency_key="p3",
        payload=json.dumps({"text": "again", "private_reply": True}),
        available_at=timezone.now(),
    )
    Message.objects.for_workspace(channel.workspace_id).create(
        workspace_id=channel.workspace_id,
        conversation=conversation,
        direction="outbound",
        text="again",
        delivery=third,
    )
    assert (dispatch(third).status, third.error_code) == ("failed", "private_reply_limit")
    # Once the private reply is closed, the window still governs the DM thread.
    conversation.last_inbound_at = timezone.now() - timedelta(hours=25)
    conversation.save()
    with patch("apps.crm.services.notify"):
        with pytest.raises(ValidationError):
            queue_reply(conversation, "late", "p4", private_reply_id="c1")


# --- Phase 5: billing reconciliation


def billing_event(workspace, event_type, obj, created=None):
    event = BillingEvent.objects.for_workspace(workspace).create(
        workspace=workspace,
        event_id="evt_" + secrets.token_hex(4),
        payload=json.dumps(
            {
                "type": event_type,
                "created": created or int(timezone.now().timestamp()),
                "data": {"object": obj},
            }
        ),
    )
    billing_tasks.process_event(str(workspace.pk), str(event.id))
    event.refresh_from_db()
    return event.status


def test_invoice_events_only_apply_to_the_tracked_open_subscription(workspace):
    account = account_for(workspace.pk)
    account.customer_id, account.subscription_id, account.status = "cus_1", "sub_1", "past_due"
    account.save()
    assert billing_event(workspace, "invoice.paid", {"subscription": "sub_other"}) == "ignored"
    assert account_for(workspace.pk).status == "past_due"
    assert billing_event(workspace, "invoice.paid", {"subscription": None}) == "ignored"
    new_shape = {"parent": {"subscription_details": {"subscription": "sub_1"}}}
    assert billing_event(workspace, "invoice.paid", new_shape) == "processed"
    assert account_for(workspace.pk).status == "active"
    assert (
        billing_event(workspace, "invoice.payment_failed", {"subscription": "sub_1"}) == "processed"
    )
    assert account_for(workspace.pk).status == "past_due"
    account.status = "canceled"
    account.save()
    assert billing_event(workspace, "invoice.paid", {"subscription": "sub_1"}) == "ignored"
    assert account_for(workspace.pk).status == "canceled"


def test_deleting_a_replaced_subscription_is_ignored(workspace):
    account = account_for(workspace.pk)
    account.customer_id, account.subscription_id, account.status = "cus_1", "sub_2", "active"
    account.save()
    old = {"id": "sub_1", "status": "canceled", "items": {"data": []}}
    assert billing_event(workspace, "customer.subscription.deleted", old) == "ignored"
    assert (account_for(workspace.pk).status, account_for(workspace.pk).subscription_id) == (
        "active",
        "sub_2",
    )
    current = {"id": "sub_2", "status": "canceled", "items": {"data": []}}
    assert billing_event(workspace, "customer.subscription.deleted", current) == "processed"
    assert account_for(workspace.pk).status == "canceled"


def test_unmapped_price_is_flagged_without_cutting_limits(workspace):
    from tests.conftest import price_for

    account = account_for(workspace.pk)
    account.customer_id = "cus_1"
    account.plan_price = price_for("starter", stripe_price_id="price_base")
    account.save()
    obj = {"id": "sub_1", "status": "active", "items": {"data": [{"price": {"id": "price_x"}}]}}
    assert billing_event(workspace, "customer.subscription.updated", obj) == "processed"
    account = account_for(workspace.pk)
    assert (account.plan, account.usage_limit, account.status) == ("unmapped", 1000, "active")
    assert (
        AuditEvent.objects.for_workspace(workspace).filter(action="billing.price_unmapped").exists()
    )


def test_sync_reconciles_drift_and_stops_metering_closed_subscriptions(workspace, settings):
    from apps.agents.models import UsageRecord
    from apps.platform_ops.tasks import sync_subscriptions
    from tests.conftest import price_for

    settings.STRIPE_SECRET_KEY = "sk_test_x"
    price_for("pro", stripe_price_id="price_pro")
    account = account_for(workspace.pk)
    account.customer_id, account.subscription_id, account.status = "cus_1", "sub_1", "active"
    account.period_start = timezone.now() - timedelta(days=1)
    account.save()
    record = UsageRecord.objects.for_workspace(workspace).create(
        workspace=workspace, key="u1", provider="openai", model="m", status="complete"
    )
    assert billing_tasks.reportable_usage().filter(pk=record.pk).exists()
    live = {
        "id": "sub_1",
        "status": "canceled",
        "items": {
            "data": [
                {
                    "price": {
                        "id": "price_pro",
                        "currency": "usd",
                        "unit_amount": 9900,
                        "recurring": {"interval": "month"},
                    }
                }
            ]
        },
    }
    with patch("apps.platform_ops.tasks.stripe.Subscription.retrieve", return_value=live):
        sync_subscriptions()
    account = account_for(workspace.pk)
    assert (account.status, account.plan, account.seat_limit) == ("canceled", "pro", 10)
    assert AuditEvent.objects.for_workspace(workspace).filter(action="billing.reconciled").exists()
    assert not billing_tasks.reportable_usage().filter(pk=record.pk).exists()
    # Nothing changed on the second pass, so nothing is re-audited.
    with patch("apps.platform_ops.tasks.stripe.Subscription.retrieve", return_value=live):
        sync_subscriptions()
    assert (
        AuditEvent.objects.for_workspace(workspace).filter(action="billing.reconciled").count() == 1
    )


# --- Phase 5: data lifecycle


def test_export_covers_every_tenant_table_and_omits_secrets(workspace, channel):
    from django.apps import apps as django_apps

    from apps.agents.models import AgentRun, AgentSession, KnowledgeChunk, VoiceAsset
    from apps.automations.models import ConversationState, Edge, Node, Trigger
    from apps.billing.models import BillingAccount, BillingJob
    from apps.marketplace.models import SellerAccount
    from apps.public_api.models import APIKey, OutboundWebhook
    from apps.tenants.data_tasks import export_tables, run_data_operation
    from apps.tenants.models import Invitation, OutboxEvent, TenantModel

    # Operational/derived tables that hold no customer content of their own.
    excluded = {
        OAuthState, WebhookEvent, Delivery, BillingAccount, BillingEvent, BillingJob,
        KnowledgeChunk, AgentSession, AgentRun, VoiceAsset, Trigger, Node, Edge,
        ConversationState, Invitation, OutboxEvent, DataOperation, OutboundWebhook,
        SellerAccount,
    }  # fmt: skip
    tenant_models = {
        model
        for model in django_apps.get_models()
        if issubclass(model, TenantModel) and not model._meta.abstract
    }
    covered = {model for model, _ in export_tables().values()}
    assert tenant_models - covered - excluded == set(), "new tenant table missing from export"

    IntegrationConfig.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider="slack",
        credentials=json.dumps({"access_token": "xoxb-secret"}),
    )
    Offer.objects.for_workspace(workspace).create(
        workspace=workspace, name="Call", amount_cents=5000
    )
    APIKey.objects.for_workspace(workspace).create(
        workspace=workspace, name="Zap", prefix="nm_abc", key_hash="h" * 64, scopes=["read"]
    )
    inbound(channel)
    job = DataOperation.objects.for_workspace(workspace).create(workspace=workspace, kind="export")
    run_data_operation(str(workspace.pk), str(job.id))
    job.refresh_from_db()
    assert job.status == "complete"
    result = json.loads(job.result)
    assert result["integrations"][0]["provider"] == "slack"
    assert result["offers"][0]["amount_cents"] == 5000
    assert result["api_keys"][0]["prefix"] == "nm_abc"
    assert result["members"][0]["role"] == "owner"
    assert len(result["leads"]) == 1 and len(result["messages"]) == 1
    assert result["manifest"]["external_systems"] == ["slack"]
    assert "xoxb-secret" not in job.result and "h" * 64 not in job.result


def test_retention_scrubs_newer_payload_stores_but_not_open_work(workspace, channel, settings):
    from apps.public_api.models import OutboundWebhook, WebhookSubscription
    from apps.tenants.data_tasks import apply_retention

    settings.RETENTION_DAYS = 30
    old = timezone.now() - timedelta(days=31)
    message = inbound(channel)
    conversation = message.conversation
    slack = IntegrationConfig.objects.for_workspace(workspace).create(
        workspace=workspace, provider="slack", credentials="{}"
    )
    done, pending = [
        IntegrationJob.objects.for_workspace(workspace).create(
            workspace=workspace,
            integration=slack,
            operation="notify",
            payload=json.dumps({"text": "Hot lead: Jane"}),
            idempotency_key=key,
            status=status,
            result=json.dumps({"id": "ts"}),
            available_at=timezone.now(),
        )
        for key, status in [("a", "complete"), ("b", "pending")]
    ]
    subscription = WebhookSubscription.objects.for_workspace(workspace).create(
        workspace=workspace, url="https://hooks.example.com/x", events=["lead.hot"], secret="s"
    )
    hook = OutboundWebhook.objects.for_workspace(workspace).create(
        workspace=workspace,
        subscription=subscription,
        event="lead.hot",
        payload=json.dumps({"name": "Jane"}),
        status="delivered",
        available_at=timezone.now(),
    )
    event = BillingEvent.objects.for_workspace(workspace).create(
        workspace=workspace,
        event_id="evt_old",
        payload=json.dumps({"type": "x"}),
        status="processed",
    )
    offer = Offer.objects.for_workspace(workspace).create(
        workspace=workspace, name="Call", amount_cents=5000
    )
    payment = Payment.objects.for_workspace(workspace).create(
        workspace=workspace,
        offer=offer,
        conversation=conversation,
        lead=conversation.identity.lead,
        amount_cents=5000,
        status="paid",
        checkout_url="https://checkout.stripe.com/x",
        idempotency_key="pay-1",
    )
    state = OAuthState.objects.for_workspace(workspace).create(
        workspace=workspace,
        user=User.objects.get(username="owner"),
        state_hash="x" * 64,
        expires_at=old,
    )
    for model in [IntegrationJob, OutboundWebhook, BillingEvent, Payment, Message]:
        model.all_objects.filter(workspace=workspace).update(created_at=old)
    apply_retention()
    for item in [done, pending, hook, event, payment, message]:
        item.refresh_from_db()
    assert (done.payload, done.result) == ("{}", "{}")
    assert "Jane" in pending.payload  # still waiting to run
    assert hook.payload == "{}" and event.payload == "{}"
    assert payment.checkout_url == "" and payment.status == "paid"
    assert message.text == ""
    assert not OAuthState.all_objects.filter(pk=state.pk).exists()


# --- Phase 4: integration credential lifecycle


def start(client, workspace, provider):
    return client.post(f"/api/workspaces/{workspace.pk}/integrations/{provider}/oauth/")


def state_of(url):
    return parse_qs(urlparse(url).query)["state"][0]


def test_fake_oauth_creates_a_test_integration_single_use(client, workspace, settings):
    assert start(client, workspace, "hubspot").status_code == 404
    started = start(client, workspace, "google_calendar")
    assert started.status_code == 200 and started.json()["mode"] == "fake"
    url = started.json()["authorization_url"]
    stranger = APIClient()
    stranger.force_authenticate(User.objects.create_user(username="s", email="s@example.com"))
    assert stranger.get(url).status_code == 400
    response = client.get(url)
    assert response.status_code == 302
    assert response["Location"].endswith("integration=test-connected")
    assert f"/w/{workspace.pk}/integrations" in response["Location"]
    assert client.get(url).status_code == 400
    config = IntegrationConfig.objects.for_workspace(workspace).get(provider="google_calendar")
    assert (config.is_test, config.enabled, config.status) == (True, True, "active")
    # A Slack state cannot complete a Google callback.
    other = state_of(start(client, workspace, "slack").json()["authorization_url"])
    assert (
        client.get(
            f"/api/integrations/callback/google_calendar/?state={other}&code=local-test-code"
        ).status_code
        == 400
    )
    settings.CHANNEL_ADAPTER_MODE = "disabled"
    assert start(client, workspace, "google_calendar").status_code == 409


def test_live_google_exchange_keeps_the_refresh_token(client, workspace, settings):
    settings.GOOGLE_CLIENT_ID, settings.GOOGLE_CLIENT_SECRET = "gid", "gsecret"
    started = start(client, workspace, "google_calendar").json()
    assert started["mode"] == "live"
    query = parse_qs(urlparse(started["authorization_url"]).query)
    assert started["authorization_url"].startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert query["redirect_uri"] == [settings.INTEGRATION_REDIRECT_BASE + "google_calendar/"]
    assert query["access_type"] == ["offline"]
    token = {"access_token": "at1", "refresh_token": "rt1", "expires_in": 3600}
    with patch("apps.crm.oauth.request", return_value=token) as req:
        response = client.get(
            f"/api/integrations/callback/google_calendar/?state={state_of(started['authorization_url'])}&code=abc"
        )
    assert response.status_code == 302 and response["Location"].endswith("integration=connected")
    assert req.call_args.kwargs["data"]["code"] == "abc"
    config = IntegrationConfig.objects.for_workspace(workspace).get(provider="google_calendar")
    assert json.loads(config.credentials)["refresh_token"] == "rt1"
    assert (config.is_test, config.status) == (False, "active")
    # Re-consent without a new refresh token must not drop the one we hold.
    again = start(client, workspace, "google_calendar").json()["authorization_url"]
    with patch("apps.crm.oauth.request", return_value={"access_token": "at2", "expires_in": 60}):
        client.get(f"/api/integrations/callback/google_calendar/?state={state_of(again)}&code=def")
    config.refresh_from_db()
    credentials = json.loads(config.credentials)
    assert (credentials["access_token"], credentials["refresh_token"]) == ("at2", "rt1")
    assert (
        AuditEvent.objects.for_workspace(workspace).filter(action="integration.connected").count()
        == 2
    )
    assert "at2" not in client.get(f"/api/workspaces/{workspace.pk}/integrations/").content.decode()


def test_slack_install_picks_the_channel_and_disconnect_revokes(client, workspace, settings):
    settings.SLACK_CLIENT_ID, settings.SLACK_CLIENT_SECRET = "sid", "ssecret"
    url = start(client, workspace, "slack").json()["authorization_url"]
    assert "incoming-webhook" in parse_qs(urlparse(url).query)["scope"][0]
    install = {
        "ok": True,
        "access_token": "xoxb-1",
        "team": {"id": "T1"},
        "incoming_webhook": {"channel_id": "C1", "channel": "#leads"},
    }
    with patch("apps.crm.oauth.request", return_value=install):
        assert (
            client.get(
                f"/api/integrations/callback/slack/?state={state_of(url)}&code=x"
            ).status_code
            == 302
        )
    config = IntegrationConfig.objects.for_workspace(workspace).get(provider="slack")
    assert config.options == {"channel_id": "C1", "channel_name": "#leads"}
    assert json.loads(config.credentials)["access_token"] == "xoxb-1"
    # The user backed out at Slack.
    cancelled = start(client, workspace, "slack").json()["authorization_url"]
    response = client.get(
        f"/api/integrations/callback/slack/?state={state_of(cancelled)}&error=access_denied"
    )
    assert response["Location"].endswith("integration=cancelled")
    # A rejected exchange never writes credentials.
    rejected = start(client, workspace, "slack").json()["authorization_url"]
    with patch("apps.crm.oauth.request", return_value={"ok": False}):
        response = client.get(
            f"/api/integrations/callback/slack/?state={state_of(rejected)}&code=y"
        )
    assert response["Location"].endswith("integration=failed")
    with patch("apps.crm.oauth.request") as req:
        response = client.delete(f"/api/workspaces/{workspace.pk}/integrations/{config.id}/")
    assert response.status_code == 200 and response.json()["status"] == "disconnected"
    assert req.call_args.args[1] == "https://slack.com/api/auth.revoke"
    config.refresh_from_db()
    assert (config.credentials, config.enabled, config.status) == ("{}", False, "disconnected")
    assert (
        AuditEvent.objects.for_workspace(workspace)
        .filter(action="integration.disconnected")
        .exists()
    )


def test_dead_google_grant_marks_reconnect_required(client, workspace):
    from apps.crm.tasks import refresh_integrations

    config = IntegrationConfig.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider="google_calendar",
        credentials=json.dumps(
            {
                "access_token": "a",
                "refresh_token": "r",
                "expires_at": (timezone.now() - timedelta(minutes=1)).isoformat(),
            }
        ),
    )
    with patch("apps.crm.integrations.request", side_effect=RetryableError(30)):
        refresh_integrations()
    config.refresh_from_db()
    assert config.status == "active"
    with patch("apps.crm.integrations.request", side_effect=ProviderError("credentials_expired")):
        refresh_integrations()
    config.refresh_from_db()
    assert config.status == "reconnect_required"
    assert (
        AuditEvent.objects.for_workspace(workspace)
        .filter(action="integration.refresh_failed")
        .count()
        == 1
    )
    # Flagged grants are not hammered again; fresh credentials clear the flag.
    with patch("apps.crm.integrations.request") as req:
        refresh_integrations()
        req.assert_not_called()
    response = client.post(
        f"/api/workspaces/{workspace.pk}/integrations/",
        {"provider": "google_calendar", "credentials": {"access_token": "new"}, "options": {}},
        format="json",
    )
    assert response.status_code == 201 and response.json()["status"] == "active"


def test_subscription_events_record_interval_and_trial_end(workspace):
    from tests.conftest import price_for

    price_for("pro", "annual", stripe_price_id="price_pro_year")
    price_for("pro", "monthly", stripe_price_id="price_pro_month")
    account = account_for(workspace.pk)
    account.customer_id = "cus_1"
    account.save()
    trial_end = int((timezone.now() + timedelta(days=7)).timestamp())
    metered = {"id": "price_meter", "recurring": {"usage_type": "metered", "interval": "month"}}
    base = {"id": "price_pro_year", "recurring": {"interval": "year", "interval_count": 1}}
    obj = {
        "id": "sub_1",
        "status": "trialing",
        "trial_end": trial_end,
        "items": {"data": [{"price": metered}, {"price": base}]},
    }
    assert billing_event(workspace, "customer.subscription.created", obj) == "processed"
    account = account_for(workspace.pk)
    assert (account.plan, account.billing_interval, account.status) == ("pro", "annual", "trialing")
    assert int(account.trial_ends_at.timestamp()) == trial_end
    obj.update(status="active", trial_end=None)
    base.update(id="price_pro_month", recurring={"interval": "month", "interval_count": 1})
    assert billing_event(workspace, "customer.subscription.updated", obj) == "processed"
    account = account_for(workspace.pk)
    assert (account.billing_interval, account.trial_ends_at) == ("monthly", None)

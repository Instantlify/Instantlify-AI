"""Prepaid AI credits: rate resolution, the ledger, runtime enforcement, auto top-up and
manual top-up checkout."""

import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
import stripe
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.agents.models import AgentConfig, AgentRun, UsageRecord
from apps.agents.providers import Completion
from apps.agents.tasks import process_run
from apps.billing import credits
from apps.billing import tasks as billing_tasks
from apps.billing.models import (
    AICreditBalance,
    AICreditTransaction,
    BillingEvent,
    BillingJob,
    ModelPricingRate,
)
from apps.billing.services import account_for, complete_usage, reserve_usage
from apps.channels.models import ChannelConnection, WebhookEvent
from apps.crm.services import receive
from apps.tenants.models import AuditEvent

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def quiet_notify():
    with patch("apps.crm.services.notify"), patch("apps.crm.tasks.notify"):
        yield


@pytest.fixture
def config(workspace):
    # A live (non-test) config on platform credits; provider calls are mocked.
    return AgentConfig.objects.for_workspace(workspace).create(
        workspace=workspace, enabled=True, model="gpt-5.4-mini", billing_mode="platform_credits"
    )


def topped_up(workspace, cents):
    return credits.credit(workspace.pk, key=f"seed:{cents}", amount_cents=cents, type="adjustment")


def rate(pattern, our_in, our_out, real_in=0, real_out=0, **fields):
    return ModelPricingRate.objects.create(
        model_pattern=pattern,
        our_input=our_in,
        our_output=our_out,
        real_input=real_in,
        real_output=real_out,
        **fields,
    )


# --- rate card


def test_seeded_rates_include_a_single_fallback():
    assert ModelPricingRate.objects.filter(is_fallback_default=True).count() == 1
    assert credits.resolve_rate("gpt-5.4-mini").model_pattern == "gpt-5.4-mini"
    assert credits.resolve_rate("something-new-2027").is_fallback_default


def test_most_specific_pattern_wins_and_fallback_is_mandatory():
    rate("claude%", 100, 200)
    rate("claude-opus%", 300, 400)
    rate("claude-opus-5", 500, 600)
    assert credits.resolve_rate("claude-opus-5").our_input == 500
    assert credits.resolve_rate("claude-opus-4").our_input == 300
    assert credits.resolve_rate("Claude-Sonnet-5").our_input == 100
    ModelPricingRate.objects.filter(is_fallback_default=True).delete()
    with pytest.raises(credits.NoPricingRate):
        credits.resolve_rate("unknown")


def test_price_keeps_sub_cent_precision():
    card = rate("tiny", 60, 240, 15, 60)
    charged, real = credits.price(card, tokens_in=50, tokens_out=10)
    assert (charged, real) == (Decimal("0.0054"), Decimal("0.0014"))


# --- ledger


def test_charge_debits_and_writes_an_auditable_row(workspace):
    topped_up(workspace, 1000)
    row = credits.charge(
        workspace.pk, key="u1", model="gpt-5.4-mini", tokens_in=100000, tokens_out=10000
    )
    assert row.amount_cents == Decimal("-8.4") and row.real_cost_cents == Decimal("2.1")
    assert row.remaining_balance_cents == Decimal("991.6")
    assert credits.balance_for(workspace.pk).balance_cents == Decimal("991.6")
    assert credits.charge(workspace.pk, key="u1", model="gpt-5.4-mini", tokens_in=1).pk == row.pk
    assert AICreditTransaction.objects.for_workspace(workspace).count() == 2  # seed + one usage


def test_complete_usage_charges_per_call_on_platform_credits(workspace, config):
    topped_up(workspace, 500)
    record = reserve_usage(config, "turn-1")
    complete_usage(record, Completion("a", [], 1000, 100), config)
    complete_usage(record, Completion("b", [], 2000, 200), config)
    record.refresh_from_db()
    rows = AICreditTransaction.objects.for_workspace(workspace).filter(type="usage")
    assert rows.count() == 2 and {r.key for r in rows} == {
        f"usage:{record.id}:1",
        f"usage:{record.id}:2",
    }
    assert (record.calls, record.input_tokens, record.billing_mode) == (2, 3000, "platform_credits")
    assert record.cost == Decimal("0.0025200000")  # dollars charged across both calls
    assert not billing_tasks.reportable_usage().filter(pk=record.pk).exists()


def test_byo_key_workspaces_are_never_debited(workspace):
    config = AgentConfig.objects.for_workspace(workspace).create(
        workspace=workspace,
        enabled=True,
        billing_mode="byo_key",
        api_key="sk-own",
        input_cost_per_million=1,
    )
    record = reserve_usage(config, "turn-byo")
    complete_usage(record, Completion("a", [], 1_000_000, 0), config)
    record.refresh_from_db()
    assert record.cost == Decimal(1) and record.calls == 1
    assert not AICreditTransaction.objects.for_workspace(workspace).exists()


def test_empty_balance_parks_the_run_as_needs_payment(workspace, config):
    with pytest.raises(PermissionDenied, match="credits_exhausted"):
        reserve_usage(config, "turn-empty")
    channel = ChannelConnection.objects.for_workspace(workspace).create(
        workspace=workspace,
        external_account_id="ig",
        display_name="ig",
        access_token="t",
        expires_at=timezone.now() + timedelta(days=30),
        is_test=True,
    )
    event = WebhookEvent.objects.for_workspace(workspace).create(
        workspace=workspace,
        connection=channel,
        event_id="e1",
        payload="{}",
        available_at=timezone.now(),
    )
    message = receive(event, {"sender_id": "lead", "text": "hello"})
    message.conversation.ai_enabled = True
    message.conversation.save()
    run = AgentRun.objects.for_workspace(workspace).create(workspace=workspace, message=message)
    with patch("apps.agents.runtime.provider_for") as provider:
        process_run(str(workspace.pk), str(run.id))
        provider.assert_not_called()
    run.refresh_from_db()
    assert (run.status, run.error_code) == ("needs_payment", "credits_exhausted")
    assert (
        AuditEvent.objects.for_workspace(workspace).filter(action="ai.credits_exhausted").exists()
    )


# --- auto top-up


def enable_auto(workspace, threshold=500, amount=2000):
    account = account_for(workspace.pk)
    account.customer_id = "cus_1"
    account.save()
    AICreditBalance.objects.for_workspace(workspace).filter(
        pk=credits.balance_for(workspace.pk).pk
    ).update(
        auto_topup_enabled=True,
        auto_topup_threshold_cents=threshold,
        auto_topup_amount_cents=amount,
        payment_method_id="pm_1",
    )


def test_auto_topup_fires_below_threshold_and_logs_the_intent(workspace, settings):
    settings.STRIPE_SECRET_KEY = "sk_test_x"
    topped_up(workspace, 600)
    enable_auto(workspace)
    intent = MagicMock(id="pi_auto", status="succeeded")
    with patch("stripe.PaymentIntent.create", return_value=intent) as create:
        credits.charge(workspace.pk, key="big", model="gpt-5.4-mini", tokens_in=5_000_000)
        credits.auto_topup_by_id(workspace.pk)  # on_commit is not run inside the test transaction
    kwargs = create.call_args.kwargs
    assert (kwargs["amount"], kwargs["off_session"], kwargs["payment_method"]) == (
        2000,
        True,
        "pm_1",
    )
    row = AICreditTransaction.objects.for_workspace(workspace).get(type="auto_topup")
    assert row.stripe_payment_intent_id == "pi_auto"
    assert credits.balance_for(workspace.pk).balance_cents == Decimal("2300")
    assert AuditEvent.objects.for_workspace(workspace).filter(action="ai.auto_topup").exists()


def test_failed_auto_topup_disables_itself_and_lets_the_run_wait(workspace, config, settings):
    settings.STRIPE_SECRET_KEY = "sk_test_x"
    enable_auto(workspace)
    with patch(
        "stripe.PaymentIntent.create",
        side_effect=stripe.CardError("declined", None, "card_declined"),
    ) as create:
        assert credits.ensure_credit(workspace.pk) is False
        create.assert_called_once()
    balance = credits.balance_for(workspace.pk)
    assert balance.auto_topup_enabled is False and balance.auto_topup_failed_at is not None
    assert (
        AuditEvent.objects.for_workspace(workspace).filter(action="ai.auto_topup_failed").exists()
    )
    with patch("stripe.PaymentIntent.create") as create:
        assert credits.ensure_credit(workspace.pk) is False
        create.assert_not_called()  # never retried silently


# --- manual top-up checkout


def test_topup_checkout_credits_on_webhook_and_saves_the_card(client, workspace, settings):
    settings.STRIPE_SECRET_KEY = "sk_test_x"
    url = f"/api/workspaces/{workspace.pk}/billing/"
    assert (
        client.post(
            url, {"kind": "credits", "amount_cents": 100}, format="json", HTTP_IDEMPOTENCY_KEY="k0"
        ).status_code
        == 400
    )
    response = client.post(
        url, {"kind": "credits", "amount_cents": 2500}, format="json", HTTP_IDEMPOTENCY_KEY="k1"
    )
    assert response.status_code == 202
    job = BillingJob.objects.for_workspace(workspace).get(request_key="k1")
    assert (job.kind, job.amount_cents) == ("credits", 2500)
    with (
        patch("stripe.Customer.create", return_value=MagicMock(id="cus_new")),
        patch(
            "stripe.checkout.Session.create", return_value=MagicMock(url="https://checkout/x")
        ) as create,
    ):
        billing_tasks.process_job(str(workspace.pk), str(job.id))
    kwargs = create.call_args.kwargs
    assert (
        kwargs["mode"] == "payment" and kwargs["line_items"][0]["price_data"]["unit_amount"] == 2500
    )
    assert kwargs["payment_intent_data"]["setup_future_usage"] == "off_session"
    pending = AICreditTransaction.objects.for_workspace(workspace).get(type="topup")
    assert pending.status == "pending" and kwargs["metadata"]["instantlify_credit_topup"] == str(
        pending.pk
    )
    payload = {
        "type": "checkout.session.completed",
        "created": int(timezone.now().timestamp()),
        "data": {
            "object": {
                "id": "cs_1",
                "payment_status": "paid",
                "amount_total": 2500,
                "payment_intent": "pi_manual",
                "metadata": {
                    "instantlify_credit_topup": str(pending.pk),
                    "workspace": str(workspace.pk),
                },
            }
        },
    }
    from apps.billing.views import event_workspace

    assert event_workspace(payload) == workspace.pk
    event = BillingEvent.objects.for_workspace(workspace).create(
        workspace=workspace, event_id="evt_topup", payload=json.dumps(payload)
    )
    with patch("stripe.PaymentIntent.retrieve", return_value={"payment_method": "pm_saved"}):
        billing_tasks.process_event(str(workspace.pk), str(event.id))
        billing_tasks.process_event(str(workspace.pk), str(event.id))  # idempotent
    pending.refresh_from_db()
    balance = credits.balance_for(workspace.pk)
    assert (pending.status, pending.stripe_payment_intent_id) == ("complete", "pi_manual")
    assert (balance.balance_cents, balance.payment_method_id) == (Decimal(2500), "pm_saved")
    body = client.get(f"/api/workspaces/{workspace.pk}/billing/credits/").json()
    assert body["has_payment_method"] and Decimal(body["balance_cents"]) == 2500
    assert body["transactions"][0]["type"] == "topup"


def test_auto_topup_settings_require_a_saved_card(client, workspace):
    url = f"/api/workspaces/{workspace.pk}/billing/credits/"
    denied = client.patch(url, {"auto_topup_enabled": True}, format="json")
    assert denied.status_code == 400 and "manual top-up first" in denied.json()[0]
    AICreditBalance.objects.for_workspace(workspace).filter(
        pk=credits.balance_for(workspace.pk).pk
    ).update(payment_method_id="pm_1")
    saved = client.patch(
        url,
        {
            "auto_topup_enabled": True,
            "auto_topup_threshold_cents": 1000,
            "auto_topup_amount_cents": 3000,
        },
        format="json",
    ).json()
    assert (
        saved["auto_topup_enabled"],
        saved["auto_topup_threshold_cents"],
        saved["auto_topup_amount_cents"],
    ) == (True, 1000, 3000)
    assert client.patch(url, {"auto_topup_amount_cents": 1}, format="json").status_code == 400


# --- embeddings and provider key


def test_embeddings_are_debited_and_platform_key_is_used(workspace, config, settings):
    from apps.agents.providers import OpenAIProvider, api_key_for
    from apps.channels.transport import ProviderError

    with pytest.raises(ProviderError, match="platform_llm_key_missing"):
        api_key_for(config)
    settings.PLATFORM_OPENAI_API_KEY = "sk-platform"
    assert OpenAIProvider(config).headers["Authorization"] == "Bearer sk-platform"
    topped_up(workspace, 100)
    from apps.agents.models import KnowledgeDocument
    from apps.agents.rag import ingest

    document = KnowledgeDocument.objects.for_workspace(workspace).create(
        workspace=workspace, title="FAQ", source="We open at nine.", file_type="text"
    )
    provider = MagicMock()
    provider.embed.return_value = ([[0.0] * 1536], 1_000_000)
    with patch("apps.agents.rag.embedder_for", return_value=provider):
        ingest(document, config)
    row = AICreditTransaction.objects.for_workspace(workspace).get(model="text-embedding-3-small")
    assert row.amount_cents == Decimal("-5") and row.tokens_in == 1_000_000
    record = UsageRecord.objects.for_workspace(workspace).get(key=f"document:{document.id}")
    assert (record.cost, record.billing_mode) == (Decimal("0.05"), "platform_credits")
    assert credits.balance_for(workspace.pk).balance_cents == Decimal("95")
    document.source = "We now open at ten."
    document.source_revision = 1
    document.save()
    with patch("apps.agents.rag.embedder_for", return_value=provider):
        ingest(document, config)
    assert (
        UsageRecord.objects.for_workspace(workspace)
        .filter(key=f"document:{document.id}:revision:1")
        .exists()
    )
    assert credits.balance_for(workspace.pk).balance_cents == Decimal("90")


# --- transcription


def test_transcription_is_charged_per_second_of_audio(workspace, config):
    from apps.billing.services import charge_transcription

    topped_up(workspace, 100)
    record = reserve_usage(config, "transcription:m1", kind="transcription")
    charge_transcription(config, record, 59.2)  # billed as 60 s
    record.refresh_from_db()
    row = AICreditTransaction.objects.for_workspace(workspace).get(type="usage")
    # Seeded whisper-1: 20,000 / 10,000 cents per million seconds.
    assert (row.model, row.tokens_in, row.key) == ("whisper-1", 60, f"usage:{record.id}:transcribe")
    assert (row.amount_cents, row.real_cost_cents) == (Decimal("-1.2"), Decimal("0.6"))
    assert credits.balance_for(workspace.pk).balance_cents == Decimal("98.8")
    assert (record.status, record.audio_seconds, record.input_tokens) == (
        "complete",
        Decimal("59.2"),
        0,
    )
    assert record.cost == Decimal("0.012")
    charge_transcription(config, record, 59.2)  # a retried job is not charged twice
    assert AICreditTransaction.objects.for_workspace(workspace).filter(type="usage").count() == 1


def test_byo_key_transcription_records_real_cost_without_debit(workspace):
    from apps.billing.services import charge_transcription

    byo = AgentConfig.objects.for_workspace(workspace).create(
        workspace=workspace, enabled=True, billing_mode="byo_key"
    )
    record = reserve_usage(byo, "transcription:m2", kind="transcription")
    charge_transcription(byo, record, 120)
    record.refresh_from_db()
    assert record.cost == Decimal("0.012")  # $0.006/min, charged by OpenAI to their key
    assert not AICreditTransaction.objects.for_workspace(workspace).exists()

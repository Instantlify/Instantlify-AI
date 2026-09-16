"""Agent tool loop, sales stage machine, triage/handoff and in-chat payments."""

import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.test import Client, override_settings
from django.utils import timezone

from apps.agents.models import AgentConfig, AgentRun, AgentSession, ToolCall
from apps.agents.providers import Completion
from apps.agents.tasks import process_run
from apps.analytics.models import FunnelEvent
from apps.automations.models import Automation, ConversationState
from apps.automations.services import publish
from apps.billing.models import Offer, Payment
from apps.billing.payments import mark_paid
from apps.channels.models import ChannelConnection, Delivery, WebhookEvent
from apps.crm.models import Conversation, IntegrationConfig, IntegrationJob
from apps.crm.services import receive
from apps.public_api.models import OutboundWebhook, WebhookSubscription

pytestmark = pytest.mark.django_db

TOOLS = [
    "check_calendar_availability",
    "book_call",
    "update_crm_field",
    "create_payment_link",
    "handoff_to_human",
]
NEUTRAL = Completion('{"sentiment":"neutral","urgency":"normal","intent":"question"}', [], 5, 5)


def triage(**fields):
    return Completion(
        json.dumps({"sentiment": "neutral", "urgency": "normal", "intent": "question", **fields}),
        [],
        5,
        5,
    )


def calling(name, args, call_id="call_1"):
    return Completion(
        "", [{"name": name, "arguments": json.dumps(args), "call_id": call_id}], 10, 5
    )


def saying(text):
    return Completion(text, [], 10, 5)


@pytest.fixture(autouse=True)
def quiet_notify():
    with patch("apps.crm.services.notify"), patch("apps.crm.tasks.notify"):
        yield


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


@pytest.fixture
def config(workspace):
    return AgentConfig.objects.for_workspace(workspace).create(
        workspace=workspace, enabled=True, is_test=True, allowed_tools=TOOLS
    )


@pytest.fixture
def calendar(workspace):
    return IntegrationConfig.objects.for_workspace(workspace).create(
        workspace=workspace, provider="calcom", is_test=True
    )


def inbound(channel, text, sender="lead-1"):
    event = WebhookEvent.objects.for_workspace(channel.workspace_id).create(
        workspace_id=channel.workspace_id,
        connection=channel,
        event_id=f"evt-{WebhookEvent.all_objects.count()}",
        payload="{}",
        available_at=timezone.now(),
    )
    message = receive(event, {"sender_id": sender, "text": text})
    conversation = message.conversation
    if not conversation.ai_enabled:
        conversation.ai_enabled = True
        conversation.save()
        AgentRun.objects.for_workspace(channel.workspace_id).get_or_create(
            message=message, defaults={"workspace_id": channel.workspace_id}
        )
    return message


def run(message, *completions):
    provider = MagicMock()
    provider.complete.side_effect = list(completions)
    with patch("apps.agents.runtime.provider_for", return_value=provider):
        process_run(
            str(message.workspace_id),
            str(AgentRun.objects.for_workspace(message.workspace_id).get(message=message).id),
        )
    return provider


def replies(channel):
    return [
        json.loads(item.payload)["text"]
        for item in Delivery.objects.for_workspace(channel.workspace_id).order_by("created_at")
    ]


def slot():
    start = timezone.now() + timedelta(days=1)
    return start.isoformat(), (start + timedelta(minutes=30)).isoformat()


def test_tool_results_are_fed_back_to_the_model(channel, config, calendar):
    start, end = slot()
    message = inbound(channel, "Is tomorrow at this time free?")
    provider = run(
        message,
        NEUTRAL,
        calling("check_calendar_availability", {"start": start, "end": end}),
        saying("Yes, that time is free. Want me to book it?"),
    )
    assert replies(channel) == ["Yes, that time is free. Want me to book it?"]
    second_round_input = provider.complete.call_args_list[2].args[0]
    outputs = [item for item in second_round_input if item.get("type") == "function_call_output"]
    assert outputs and json.loads(outputs[0]["output"])["available"] is True
    assert outputs[0]["call_id"] == "call_1"
    run_row = AgentRun.objects.for_workspace(channel.workspace_id).get(message=message)
    assert run_row.status == "complete"
    checkpoint = json.loads(run_row.checkpoint)
    assert checkpoint["rounds"] == 1 and "round:1" in checkpoint


def test_repeated_failing_call_stops_the_loop(channel, config):
    start, end = slot()
    message = inbound(channel, "free?")
    same = calling("check_calendar_availability", {"start": start, "end": end})
    provider = run(message, NEUTRAL, same, same, same, same, same, same)
    assert ToolCall.objects.for_workspace(channel.workspace_id).count() == 1
    assert provider.complete.call_count == 3  # triage, first attempt, repeat detected
    assert "team member" in replies(channel)[-1]


def test_tool_round_budget_and_no_tools_on_final_round(channel, config):
    config.max_tool_rounds = 2
    config.save()
    message = inbound(channel, "hi")
    call = calling("update_crm_field", {"field": "interest", "value": "x"})
    other = calling("update_crm_field", {"field": "budget", "value": "y"}, call_id="c2")
    third = calling("update_crm_field", {"field": "timeline", "value": "z"}, call_id="c3")
    provider = run(message, NEUTRAL, call, other, third)
    final_tools = provider.complete.call_args_list[3].args[1]
    assert final_tools == []
    assert ToolCall.objects.for_workspace(channel.workspace_id).count() == 2
    assert replies(channel)[-1] == "I couldn't complete that request. A team member will follow up."


def test_stage_machine_advances_on_code_signals_not_prose(channel, config):
    config.qualifying_fields = ["interest"]
    config.save()
    message = inbound(channel, "Tell me more")
    run(message, NEUTRAL, saying("Happy to. What are you looking for?"))
    session = AgentSession.objects.for_workspace(channel.workspace_id).get()
    lead = message.conversation.identity.lead
    assert session.stage == "qualify" and lead.stage == "new"

    second = inbound(channel, "Coaching for my team")
    run(
        second,
        NEUTRAL,
        calling("update_crm_field", {"field": "interest", "value": "team coaching"}),
        saying("Noted!"),
    )
    session.refresh_from_db()
    assert session.stage == "qualify"  # transition applies on the next turn's evaluation

    third = inbound(channel, "What does it cost?")
    run(third, NEUTRAL, saying("Here is our offer."))
    session.refresh_from_db()
    lead.refresh_from_db()
    assert (session.stage, lead.stage) == ("pitch", "qualified")

    fourth = inbound(channel, "Too expensive")
    run(fourth, triage(intent="objection"), saying("I understand."))
    session.refresh_from_db()
    assert session.stage == "objection_handling"

    fifth = inbound(channel, "Ok let's book")
    run(fifth, triage(intent="ready_to_book"), saying("Great, when suits?"))
    session.refresh_from_db()
    assert session.stage == "book"


def test_keyword_handoff_is_deterministic_and_pauses_everything(channel, config, workspace, user):
    IntegrationConfig.objects.for_workspace(workspace).create(
        workspace=workspace, provider="slack", is_test=True
    )
    sub = WebhookSubscription.objects.for_workspace(workspace).create(
        workspace=workspace,
        url="https://example.com/hook",
        events=["conversation.handoff"],
        secret="s",
    )
    automation = Automation.objects.for_workspace(workspace).create(workspace=workspace, name="x")
    publish(
        automation,
        {
            "start": "wait",
            "triggers": [{"kind": "dm", "keyword": "start"}],
            "nodes": [
                {"id": "wait", "data": {"kind": "wait"}},
                {"id": "end", "data": {"kind": "end"}},
            ],
            "edges": [{"source": "wait", "target": "end"}],
        },
        user,
    )
    message = inbound(channel, "I want a REFUND now")
    provider = run(message, saying("should not be called"))
    provider.complete.assert_not_called()
    conversation = Conversation.objects.for_workspace(workspace).get()
    assert (conversation.status, conversation.ai_enabled) == ("needs_human", False)
    assert replies(channel)[-1].startswith("I'm bringing a team member")
    assert IntegrationJob.objects.for_workspace(workspace).filter(operation="notify").count() == 1
    assert OutboundWebhook.objects.for_workspace(workspace).filter(subscription=sub).count() == 1
    assert FunnelEvent.objects.for_workspace(workspace).filter(kind="handoff").count() == 1
    # A later message must not re-open AI or re-page the team.
    event = WebhookEvent.objects.for_workspace(workspace).create(
        workspace=workspace,
        connection=channel,
        event_id="later",
        payload="{}",
        available_at=timezone.now(),
    )
    later = receive(event, {"sender_id": "lead-1", "text": "hello?"})
    assert not AgentRun.objects.for_workspace(workspace).filter(message=later).exists()
    assert IntegrationJob.objects.for_workspace(workspace).filter(operation="notify").count() == 1


def test_llm_triage_hands_off_angry_or_urgent_customers(channel, config, workspace):
    message = inbound(channel, "this is unacceptable")
    provider = run(message, triage(sentiment="angry"), saying("nope"))
    assert provider.complete.call_count == 1
    assert Conversation.objects.for_workspace(workspace).get().status == "needs_human"


def test_triage_can_be_disabled_and_bad_json_is_neutral(channel, config, workspace):
    message = inbound(channel, "hey")
    run(message, saying("not json at all"), saying("Hello!"))
    assert Conversation.objects.for_workspace(workspace).get().status == "open"
    assert replies(channel)[-1] == "Hello!"
    config.triage_enabled = False
    config.save()
    second = inbound(channel, "hey again")
    provider = run(second, saying("Hi!"))
    assert provider.complete.call_count == 1


def test_agent_requested_handoff_tool(channel, config, workspace):
    message = inbound(channel, "I need to speak to someone about a legal matter")
    run(message, NEUTRAL, calling("handoff_to_human", {"reason": "legal"}), saying("ignored"))
    assert Conversation.objects.for_workspace(workspace).get().status == "needs_human"
    assert replies(channel)[-1].startswith("I'm bringing a team member")
    assert ToolCall.objects.for_workspace(workspace).get().status == "complete"


@pytest.fixture
def stripe_test(workspace):
    return IntegrationConfig.objects.for_workspace(workspace).create(
        workspace=workspace, provider="stripe", is_test=True
    )


@pytest.fixture
def offer(workspace):
    return Offer.objects.for_workspace(workspace).create(
        workspace=workspace, name="Starter pack", amount_cents=4900
    )


def test_agent_can_only_sell_configured_offers(channel, config, workspace, stripe_test, offer):
    message = inbound(channel, "I'll take it")
    run(
        message,
        NEUTRAL,
        calling("create_payment_link", {"offer_id": str(workspace.pk)}),  # not an offer
        calling("create_payment_link", {"offer_id": str(offer.pk)}, call_id="c2"),
        saying("Here is your secure checkout link."),
    )
    payment = Payment.objects.for_workspace(workspace).get()
    assert (payment.status, payment.amount_cents, payment.offer_id) == ("pending", 4900, offer.pk)
    statuses = sorted(ToolCall.objects.for_workspace(workspace).values_list("status", flat=True))
    assert statuses == ["complete", "failed"]
    assert replies(channel)[-1] == "Here is your secure checkout link."


def test_inactive_offer_and_missing_stripe_are_refused(channel, config, workspace, offer):
    message = inbound(channel, "buy")
    run(message, NEUTRAL, calling("create_payment_link", {"offer_id": str(offer.pk)}), saying("x"))
    assert not Payment.objects.for_workspace(workspace).exists()
    call = ToolCall.objects.for_workspace(workspace).get()
    assert json.loads(call.output) == {"error": "payments_not_connected"}


def test_paid_checkout_marks_lead_won_and_records_revenue(
    channel, config, workspace, stripe_test, offer
):
    WebhookSubscription.objects.for_workspace(workspace).create(
        workspace=workspace, url="https://example.com/h", events=["payment.paid"], secret="s"
    )
    message = inbound(channel, "buy")
    run(message, NEUTRAL, calling("create_payment_link", {"offer_id": str(offer.pk)}), saying("ok"))
    payment = Payment.objects.for_workspace(workspace).get()
    mark_paid(workspace.pk, payment.checkout_session_id, 4900)
    mark_paid(workspace.pk, payment.checkout_session_id, 4900)
    payment.refresh_from_db()
    assert payment.status == "paid" and payment.paid_at
    assert (
        message.conversation.identity.lead.__class__.objects.for_workspace(workspace).get().stage
        == "won"
    )
    assert FunnelEvent.objects.for_workspace(workspace).filter(kind="paid").count() == 1
    assert (
        OutboundWebhook.objects.for_workspace(workspace).filter(event="payment.paid").count() == 1
    )


def test_human_can_send_payment_link_into_conversation(
    client, channel, workspace, stripe_test, offer
):
    message = inbound(channel, "hi")
    response = client.post(
        f"/api/workspaces/{workspace.pk}/conversations/{message.conversation_id}/payment-link/",
        {"offer": offer.pk},
        format="json",
        HTTP_IDEMPOTENCY_KEY="once",
    )
    assert response.status_code == 202, response.content
    assert Payment.objects.for_workspace(workspace).count() == 1
    assert "Starter pack" in replies(channel)[-1]
    again = client.post(
        f"/api/workspaces/{workspace.pk}/conversations/{message.conversation_id}/payment-link/",
        {"offer": offer.pk},
        format="json",
        HTTP_IDEMPOTENCY_KEY="once",
    )
    assert again.status_code == 202 and Payment.objects.for_workspace(workspace).count() == 1


@override_settings(CHANNEL_ADAPTER_MODE="live")
def test_tenant_stripe_webhook_requires_a_valid_signature(workspace):
    IntegrationConfig.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider="stripe",
        credentials=json.dumps({"secret_key": "sk", "webhook_secret": "whsec_x"}),
    )
    response = Client().post(
        f"/webhooks/stripe/{workspace.pk}/",
        b"{}",
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE="bad",
    )
    assert response.status_code == 400
    assert (
        Client()
        .post(f"/webhooks/stripe/{workspace.pk}/", b"{}", content_type="application/json")
        .status_code
        == 400
    )


def test_offer_validation(client, workspace):
    url = f"/api/workspaces/{workspace.pk}/offers/"
    assert client.post(url, {"name": "x", "amount_cents": 10}, format="json").status_code == 400
    assert (
        client.post(
            url, {"name": "x", "amount_cents": 500, "currency": "xyz"}, format="json"
        ).status_code
        == 400
    )
    created = client.post(
        url, {"name": "Pack", "amount_cents": 500, "currency": "EUR"}, format="json"
    )
    assert created.status_code == 201 and created.json()["currency"] == "eur"


def test_handoff_stops_running_automation(channel, config, workspace, user):
    automation = Automation.objects.for_workspace(workspace).create(workspace=workspace, name="x")
    publish(
        automation,
        {
            "start": "wait",
            "triggers": [{"kind": "dm", "keyword": "start"}],
            "nodes": [
                {"id": "wait", "data": {"kind": "wait"}},
                {"id": "end", "data": {"kind": "end"}},
            ],
            "edges": [{"source": "wait", "target": "end"}],
        },
        user,
    )
    event = WebhookEvent.objects.for_workspace(workspace).create(
        workspace=workspace,
        connection=channel,
        event_id="s",
        payload="{}",
        available_at=timezone.now(),
    )
    message = receive(event, {"sender_id": "lead-9", "text": "start", "kind": "dm"})
    from apps.automations.tasks import step

    state = ConversationState.objects.for_workspace(workspace).get()
    step(str(workspace.pk), str(state.id))
    state.refresh_from_db()
    assert state.status == "waiting"
    from apps.agents.runtime import hand_off

    hand_off(message.conversation, reason="test")
    state.refresh_from_db()
    assert (state.status, state.error_code) == ("stopped", "handoff")


def test_agent_still_answers_during_automation_cooldown(channel, config, workspace, user):
    automation = Automation.objects.for_workspace(workspace).create(workspace=workspace, name="x")
    publish(
        automation,
        {
            "start": "hi",
            "triggers": [{"kind": "dm", "keyword": "price"}],
            "nodes": [
                {"id": "hi", "data": {"kind": "send_message", "text": "Prices!"}},
                {"id": "end", "data": {"kind": "end"}},
            ],
            "edges": [{"source": "hi", "target": "end"}],
        },
        user,
    )
    from apps.automations.tasks import step

    first = inbound(channel, "price")  # matches the flow; AI is enabled by the helper
    state = ConversationState.objects.for_workspace(workspace).get()
    for _ in range(3):  # send → end → completed
        step(str(workspace.pk), str(state.id))
    state.refresh_from_db()
    assert state.status == "completed" and state.cooldown_until > timezone.now()
    assert first.conversation_id == state.conversation_id
    # Another "price" inside the cooldown must not restart the flow…
    again = inbound(channel, "price again")
    assert ConversationState.objects.for_workspace(workspace).count() == 1
    state.refresh_from_db()
    assert state.status == "completed"
    # …but the agent still gets to answer it.
    assert AgentRun.objects.for_workspace(workspace).filter(message=again).exists()
    run(again, NEUTRAL, saying("Happy to help with pricing."))
    assert replies(channel)[-1] == "Happy to help with pricing."

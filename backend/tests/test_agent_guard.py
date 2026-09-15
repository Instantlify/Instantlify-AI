"""Deterministic guards around model-proposed tool calls (apps.agents.tools/runtime)."""

import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.agents.models import AgentConfig, AgentRun, ToolCall
from apps.agents.providers import Completion
from apps.agents.tasks import process_run
from apps.agents.tools import execute, propose, validate_args
from apps.billing.services import account_for
from apps.channels.models import ChannelConnection, Delivery, WebhookEvent
from apps.crm.models import IntegrationConfig
from apps.crm.services import receive
from apps.tenants.models import AuditEvent

pytestmark = pytest.mark.django_db

TOOLS = ["check_calendar_availability", "book_call", "update_crm_field"]


def slot(hours=24, minutes=30):
    start = timezone.now() + timedelta(hours=hours)
    return start.isoformat(), (start + timedelta(minutes=minutes)).isoformat()


def booking(**overrides):
    start, end = slot()
    return {"start": start, "end": end, "email": "lead@example.com", "name": "Lee", **overrides}


@pytest.fixture(autouse=True)
def quiet_notify():
    with patch("apps.crm.services.notify"):
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


def run_for(message):
    return AgentRun.objects.for_workspace(message.workspace_id).get(message=message)


def llm(*calls, text=""):
    provider = MagicMock()
    provider.complete.return_value = Completion(
        text, [{"name": name, "arguments": json.dumps(args)} for name, args in calls], 10, 5
    )
    return patch("apps.agents.runtime.provider_for", return_value=provider)


def replies(channel):
    return [
        json.loads(item.payload)["text"]
        for item in Delivery.objects.for_workspace(channel.workspace_id).order_by("created_at")
    ]


def test_booking_needs_the_customers_exact_code_then_books_once(channel, config, calendar):
    first = inbound(channel, "Can I book tomorrow?")
    with llm(("book_call", booking())):
        process_run(str(first.workspace_id), str(run_for(first).id))
    call = ToolCall.objects.for_workspace(channel.workspace_id).get()
    assert call.status == "awaiting_confirmation"
    assert f"confirm {call.confirmation_code}" in replies(channel)[-1]

    with patch("apps.crm.integrations.FakeIntegration.execute", autospec=True) as adapter:
        adapter.side_effect = lambda self, op, payload, key: (
            {"available": True} if op == "check_calendar_availability" else {"id": "bk-1"}
        )
        wrong = inbound(channel, "yes please book it")
        with llm(text="Please reply with the code."):
            process_run(str(wrong.workspace_id), str(run_for(wrong).id))
        assert adapter.call_count == 0

        confirm = inbound(channel, f"  CONFIRM {call.confirmation_code} ")
        process_run(str(confirm.workspace_id), str(run_for(confirm).id))
        assert [c.args[1] for c in adapter.call_args_list] == [
            "check_calendar_availability",
            "book_call",
        ]
        assert execute(call, config, customer_message=confirm) == {"id": "bk-1"}
        assert adapter.call_count == 2  # the completed call is not executed again

    call.refresh_from_db()
    assert call.status == "complete"
    assert replies(channel)[-1].startswith("Your call is booked.")
    assert (
        confirm.conversation.identity.lead.__class__.objects.for_workspace(channel.workspace_id)
        .get()
        .stage
        == "booked"
    )
    assert (
        AuditEvent.objects.for_workspace(channel.workspace_id)
        .filter(action="agent.tool_completed", target_id=str(call.id))
        .exists()
    )


def proposed_booking(channel, config):
    message = inbound(channel, "book")
    run = run_for(message)
    propose(run, "book_call", booking(), config)
    return message, ToolCall.objects.for_workspace(channel.workspace_id).get()


def test_booking_without_confirmation_message_is_refused(channel, config, calendar):
    _, call = proposed_booking(channel, config)
    with patch("apps.crm.integrations.integration_for") as integration:
        with pytest.raises(ValueError, match="explicit_customer_confirmation_required"):
            execute(call, config)
        integration.assert_not_called()


def test_confirmation_from_another_conversation_is_refused(channel, config, calendar):
    _, call = proposed_booking(channel, config)
    other = inbound(channel, f"confirm {call.confirmation_code}", sender="someone-else")
    with patch("apps.crm.integrations.integration_for") as integration:
        with pytest.raises(ValueError, match="explicit_customer_confirmation_required"):
            execute(call, config, customer_message=other)
        integration.assert_not_called()


def test_expired_confirmation_is_refused(channel, config, calendar):
    message, call = proposed_booking(channel, config)
    call.expires_at = timezone.now() - timedelta(seconds=1)
    call.save()
    message.text = f"confirm {call.confirmation_code}"
    with pytest.raises(ValueError, match="explicit_customer_confirmation_required"):
        execute(call, config, customer_message=message)


def test_tool_removed_from_config_cannot_execute(channel, config, calendar):
    message, call = proposed_booking(channel, config)
    config.allowed_tools = ["update_crm_field"]
    message.text = f"confirm {call.confirmation_code}"
    with pytest.raises(ValueError, match="tool_execution_guard"):
        execute(call, config, customer_message=message)


def test_disallowed_tool_is_rejected_and_audited(channel, config):
    config.allowed_tools = ["update_crm_field"]
    run = run_for(inbound(channel, "hi"))
    with pytest.raises(ValueError, match="tool_not_allowed"):
        propose(run, "book_call", booking(), config)
    call = ToolCall.objects.for_workspace(channel.workspace_id).get()
    assert call.status == "rejected"
    assert json.loads(call.output) == {"error": "tool_not_allowed"}


def test_crm_updates_are_limited_to_allowlisted_fields(channel, config):
    message = inbound(channel, "hi")
    run = run_for(message)
    with pytest.raises(ValueError, match="crm_field_not_allowed"):
        propose(run, "update_crm_field", {"field": "opted_out", "value": "false"}, config)
    assert propose(run, "update_crm_field", {"field": "budget", "value": "5k"}, config) == {
        "updated": "budget"
    }
    lead = message.conversation.identity.lead
    lead.refresh_from_db()
    assert lead.fields == {"budget": "5k"}
    assert not lead.opted_out


@pytest.mark.parametrize(
    "name,args",
    [
        ("book_call", booking(start=slot(hours=-1)[0])),
        ("book_call", booking(start="2030-01-01T10:00:00", end="2030-01-01T10:30:00")),
        ("book_call", booking(end=slot(minutes=5)[1])),
        ("book_call", booking(end=slot(minutes=60 * 9)[1])),
        ("book_call", booking(email="not-an-email")),
        ("book_call", {**booking(), "extra": "x"}),
        ("check_calendar_availability", {"start": "tomorrow", "end": "later"}),
        ("update_crm_field", {"field": "budget", "value": 5}),
        ("refund_payment", {"amount": "100"}),
    ],
)
def test_invalid_tool_arguments_are_rejected(name, args):
    from django.core.exceptions import ValidationError

    with pytest.raises((ValueError, ValidationError)):
        validate_args(name, args)


def test_rejected_tool_call_still_replies_to_the_lead(channel, config):
    message = inbound(channel, "book me")
    with llm(("book_call", booking(email="bad")), text="Booked!"):
        process_run(str(message.workspace_id), str(run_for(message).id))
    assert run_for(message).error_code == ""
    assert run_for(message).status == "complete"
    assert replies(channel) == ["I couldn't complete that request. A team member will follow up."]
    assert ToolCall.objects.for_workspace(channel.workspace_id).get().status == "rejected"


def test_unconnected_calendar_fails_the_tool_not_the_conversation(channel, config):
    message = inbound(channel, "is tomorrow free?")
    start, end = slot()
    with llm(("check_calendar_availability", {"start": start, "end": end})):
        process_run(str(message.workspace_id), str(run_for(message).id))
    call = ToolCall.objects.for_workspace(channel.workspace_id).get()
    assert call.status == "failed"
    assert "team member" in replies(channel)[-1]


def test_usage_limit_blocks_the_model_call(channel, config):
    account = account_for(channel.workspace_id)
    account.usage_limit = 0
    account.save()
    message = inbound(channel, "hello")
    with llm(text="hi") as provider_for:
        process_run(str(message.workspace_id), str(run_for(message).id))
        provider_for.return_value.complete.assert_not_called()
    assert run_for(message).status == "needs_review"
    assert replies(channel) == []


def test_opted_out_lead_is_skipped(channel, config):
    message = inbound(channel, "hello")
    lead = message.conversation.identity.lead
    lead.opted_out = True
    lead.save()
    with llm(text="hi") as provider_for:
        process_run(str(message.workspace_id), str(run_for(message).id))
        provider_for.return_value.complete.assert_not_called()
    assert run_for(message).status == "skipped"

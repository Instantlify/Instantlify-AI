"""MCP server: handshake, tool discovery, scoped tool calls, tenancy and the console count."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.automations.models import Automation, ConversationState
from apps.automations.services import publish
from apps.channels.models import ChannelConnection, Delivery, WebhookEvent
from apps.crm.services import receive
from apps.public_api.auth import generate_key
from apps.public_api.models import APIKey, MCPClient
from apps.tenants.services import create_workspace

pytestmark = pytest.mark.django_db
URL = "/api/mcp/"


@pytest.fixture(autouse=True)
def quiet_notify():
    with patch("apps.crm.services.notify"):
        yield


def key_for(workspace, scopes=("read", "write")):
    raw, prefix, digest = generate_key()
    APIKey.objects.for_workspace(workspace).create(
        workspace=workspace, name="Claude", prefix=prefix, key_hash=digest, scopes=list(scopes)
    )
    return raw


def rpc(raw, method, params=None, request_id=1, **headers):
    client = APIClient()
    body = {"jsonrpc": "2.0", "method": method}
    if request_id is not None:
        body["id"] = request_id
    if params is not None:
        body["params"] = params
    return client.post(URL, body, format="json", HTTP_AUTHORIZATION=f"Bearer {raw}", **headers)


def call(raw, name, arguments):
    return rpc(raw, "tools/call", {"name": name, "arguments": arguments}).json()["result"]


@pytest.fixture
def conversation(workspace):
    channel = ChannelConnection.objects.for_workspace(workspace).create(
        workspace=workspace,
        external_account_id="ig",
        display_name="Test",
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
    return receive(event, {"sender_id": "lead-1", "text": "hello", "kind": "dm"}).conversation


def test_handshake_records_the_client_and_lists_tools(workspace):
    raw = key_for(workspace)
    init = rpc(
        raw,
        "initialize",
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "claude-ai", "version": "1.2"},
        },
    )
    assert init.status_code == 200
    result = init.json()["result"]
    assert result["protocolVersion"] == "2025-06-18"  # the client's version, since we speak it
    assert result["capabilities"]["tools"] == {"listChanged": False}
    client = MCPClient.objects.for_workspace(workspace).get()
    assert (client.client_name, client.client_version) == ("claude-ai", "1.2")
    # An unknown version is answered with ours, never an error.
    other = rpc(raw, "initialize", {"protocolVersion": "1999-01-01", "clientInfo": {"name": "x"}})
    assert other.json()["result"]["protocolVersion"] == "2025-11-25"

    assert rpc(raw, "notifications/initialized", request_id=None).status_code == 202
    tools = {t["name"]: t for t in rpc(raw, "tools/list").json()["result"]["tools"]}
    assert set(tools) == {
        "list_conversations",
        "get_conversation_messages",
        "get_lead_details",
        "get_workspace_metrics",
        "send_message",
        "trigger_automation",
    }
    assert tools["send_message"]["annotations"]["readOnlyHint"] is False
    assert tools["list_conversations"]["inputSchema"]["type"] == "object"
    assert rpc(raw, "ping").json()["result"] == {}
    assert rpc(raw, "resources/list").json()["error"]["code"] == -32601


def test_auth_transport_rules(workspace):
    assert APIClient().post(URL, {}, format="json").status_code == 401
    raw = key_for(workspace)
    assert APIClient().get(URL, HTTP_AUTHORIZATION=f"Bearer {raw}").status_code == 405
    bad = rpc(raw, "ping", HTTP_MCP_PROTOCOL_VERSION="2020-01-01")
    assert bad.status_code == 400
    # X-API-Key works too, for clients that send a custom header.
    alt = APIClient().post(
        URL, {"jsonrpc": "2.0", "id": 1, "method": "ping"}, format="json", HTTP_X_API_KEY=raw
    )
    assert alt.status_code == 200


def test_read_tools(workspace, conversation):
    raw = key_for(workspace, scopes=("read",))
    listed = call(raw, "list_conversations", {"status": "open"})
    assert not listed["isError"]
    [row] = listed["structuredContent"]["conversations"]
    assert row["id"] == str(conversation.pk)
    messages = call(raw, "get_conversation_messages", {"conversation_id": str(conversation.pk)})
    assert messages["structuredContent"]["messages"][0]["text"] == "hello"
    lead = call(raw, "get_lead_details", {"lead_id": str(conversation.identity.lead_id)})
    assert lead["structuredContent"]["id"] == str(conversation.identity.lead_id)
    metrics = call(raw, "get_workspace_metrics", {"window_days": 7})["structuredContent"]
    assert (metrics["messages_received"], metrics["new_leads"]) == (1, 1)
    # Bad input is a tool error the model can read and correct, not a protocol failure.
    wrong = call(raw, "get_lead_details", {"lead_id": "not-a-uuid"})
    assert wrong["isError"] and "UUID" in wrong["content"][0]["text"]


def test_write_tools_need_the_write_scope(workspace, conversation):
    read_only = key_for(workspace, scopes=("read",))
    denied = call(
        read_only, "send_message", {"conversation_id": str(conversation.pk), "text": "Hi"}
    )
    assert denied["isError"] and "'write' scope" in denied["content"][0]["text"]
    assert not Delivery.objects.for_workspace(workspace).exists()

    raw = key_for(workspace)
    args = {"conversation_id": str(conversation.pk), "text": "Thanks for writing!"}
    sent = call(raw, "send_message", args)
    assert not sent["isError"]
    call(raw, "send_message", args)  # a retried call does not message twice
    assert Delivery.objects.for_workspace(workspace).count() == 1


def test_trigger_automation(workspace, user, conversation):
    raw = key_for(workspace)
    automation = Automation.objects.for_workspace(workspace).create(workspace=workspace, name="x")
    args = {"automation_id": str(automation.pk), "conversation_id": str(conversation.pk)}
    assert call(raw, "trigger_automation", args)["isError"]  # not published yet
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
    started = call(raw, "trigger_automation", args)
    assert not started["isError"] and started["structuredContent"]["started"]
    state = ConversationState.objects.for_workspace(workspace).get()
    assert (state.status, state.node_id) == ("running", "hi")
    again = call(raw, "trigger_automation", args)
    assert again["isError"] and "already running" in again["content"][0]["text"]


def test_keys_only_reach_their_own_workspace(workspace, user, conversation):
    other = create_workspace(user, "Other")
    raw = key_for(other)
    miss = call(raw, "get_conversation_messages", {"conversation_id": str(conversation.pk)})
    assert miss["isError"]
    assert call(raw, "list_conversations", {})["structuredContent"]["conversations"] == []


def test_console_counts_recently_active_clients(workspace):
    from apps.platform_ops.metrics import PlatformMetricsService

    raw = key_for(workspace)
    rpc(raw, "initialize", {"protocolVersion": "2025-06-18", "clientInfo": {"name": "claude-code"}})
    assert PlatformMetricsService(days=7).mcp() == {"clients": 1, "workspaces": 1}
    MCPClient.objects.for_workspace(workspace).update(
        last_active_at=timezone.now() - timedelta(days=10)
    )
    assert PlatformMetricsService(days=7).mcp()["clients"] == 0
    assert PlatformMetricsService(days=30).mcp()["clients"] == 1

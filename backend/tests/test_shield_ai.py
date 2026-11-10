"""AI comment-shield rules and public moderation replies."""

from unittest.mock import Mock, patch

import pytest

from apps.agents.models import AgentConfig, UsageRecord
from apps.agents.providers import Completion
from apps.automations.models import ConversationState
from apps.channels.adapters import FakeChannelAdapter
from apps.tools.models import ShieldEvent
from tests.conftest import set_limits
from tests.test_tools import connect, inbound

pytestmark = pytest.mark.django_db


@pytest.fixture
def config(workspace):
    set_limits(workspace, ai_agent_enabled=True)
    return AgentConfig.objects.for_workspace(workspace).create(
        workspace=workspace, enabled=True, is_test=True
    )


def rules_url(workspace):
    return f"/api/workspaces/{workspace.pk}/shield/rules/"


def add_ai_rule(client, workspace, **extra):
    res = client.post(
        rules_url(workspace),
        {"name": "Abuse", "prompt": "insulting or harassing the brand", "action": "hide", **extra},
        format="json",
    )
    assert res.status_code == 201, res.content
    return res.json()


def test_ai_rule_hides_comment_the_model_flags_and_replies(client, workspace, config, settings):
    settings.CHANNEL_ADAPTER_MODE = "fake"
    add_ai_rule(client, workspace, reply_text="Please DM us so we can help.")
    channel = connect(workspace)
    adapter = FakeChannelAdapter()
    model = Mock()
    model.complete.side_effect = [
        Completion('{"match": 1}', [], 20, 3),
        Completion('{"match": null}', [], 20, 3),
    ]
    with (
        patch("apps.channels.adapters.adapter_for", return_value=adapter),
        patch("apps.agents.providers.provider_for", return_value=model),
    ):
        inbound(channel, "you people are useless frauds", kind="comment", comment_id="c-1")
        inbound(channel, "Love this!", kind="comment", comment_id="c-2", sender="lead-2")
    assert adapter.moderated == [("hide", "c-1")]
    assert any("Please DM us so we can help." in str(v) for v in adapter.sent.values())
    event = ShieldEvent.objects.for_workspace(workspace).get()
    assert (event.comment_id, event.action_taken) == ("c-1", "hidden+replied")
    assert (
        "a comment that is insulting or harassing the brand"
        in (model.complete.call_args_list[0].args[0][0]["content"])
    )
    assert UsageRecord.objects.for_workspace(workspace).filter(kind="moderation").count() == 2
    assert not ConversationState.objects.for_workspace(workspace).exists()


def test_keyword_rules_run_first_and_skip_the_model(client, workspace, config, settings):
    settings.CHANNEL_ADAPTER_MODE = "fake"
    add_ai_rule(client, workspace)
    client.post(
        rules_url(workspace),
        {"name": "Spam", "keywords": ["crypto"], "action": "delete"},
        format="json",
    )
    channel = connect(workspace)
    adapter = FakeChannelAdapter()
    model = Mock()
    with (
        patch("apps.channels.adapters.adapter_for", return_value=adapter),
        patch("apps.agents.providers.provider_for", return_value=model),
    ):
        inbound(channel, "free crypto here", kind="comment", comment_id="c-1")
    assert adapter.moderated == [("delete", "c-1")]
    model.complete.assert_not_called()


def test_ai_failure_leaves_the_comment_alone(client, workspace, settings):
    settings.CHANNEL_ADAPTER_MODE = "fake"
    # No AI configuration saved: the AI rule cannot run, so nothing is hidden.
    add_ai_rule(client, workspace)
    channel = connect(workspace)
    adapter = FakeChannelAdapter()
    with patch("apps.channels.adapters.adapter_for", return_value=adapter):
        inbound(channel, "you are frauds", kind="comment", comment_id="c-1")
    assert adapter.moderated == []
    assert not ShieldEvent.objects.for_workspace(workspace).exists()


@pytest.mark.parametrize(
    "body",
    [
        {"name": "x", "keywords": [], "prompt": "", "action": "hide"},
        {"name": "x", "prompt": "abc", "action": "hide"},
        {"name": "x", "keywords": ["a"], "action": "delete", "reply_text": "hi"},
    ],
)
def test_rule_validation(client, workspace, body):
    assert client.post(rules_url(workspace), body, format="json").status_code == 400

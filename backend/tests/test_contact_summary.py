from unittest.mock import Mock, patch

import pytest

from apps.agents.models import AgentConfig, UsageRecord
from apps.agents.providers import Completion
from apps.crm.models import Lead
from tests.conftest import set_limits
from tests.test_automation_runtime import channel, inbound, quiet_notify  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture
def config(workspace):
    set_limits(workspace, ai_agent_enabled=True)
    return AgentConfig.objects.for_workspace(workspace).create(
        workspace=workspace, enabled=True, is_test=True
    )


def url(workspace, lead):
    return f"/api/workspaces/{workspace.pk}/leads/{lead.pk}/summary/"


def test_summary_is_written_from_messages_saved_and_metered(client, workspace, channel, config):  # noqa: F811
    inbound(channel, "Hi, I need pricing for 20 seats")
    inbound(channel, "Budget is tight though")
    lead = Lead.objects.for_workspace(workspace).get()
    model = Mock()
    model.complete.return_value = Completion("- Wants 20 seats\n- Price sensitive", [], 80, 12)
    with patch("apps.agents.providers.provider_for", return_value=model):
        res = client.post(url(workspace, lead), {}, format="json")
    assert res.status_code == 200, res.content
    assert res.json()["ai_summary"] == "- Wants 20 seats\n- Price sensitive"
    prompt = model.complete.call_args.args[0]
    assert "untrusted data" in prompt[0]["content"]
    assert "Customer: Hi, I need pricing for 20 seats" in prompt[1]["content"]
    assert "Customer: Budget is tight though" in prompt[1]["content"]
    lead.refresh_from_db()
    assert lead.ai_summary.startswith("- Wants") and lead.ai_summary_at is not None
    usage = UsageRecord.objects.for_workspace(workspace).get(key__startswith="summary:")
    assert usage.calls == 1 and usage.input_tokens == 80
    detail = client.get(f"/api/workspaces/{workspace.pk}/leads/{lead.pk}/").json()
    assert detail["ai_summary"] == lead.ai_summary


def test_summary_needs_messages_and_ai_configuration(client, workspace, channel):  # noqa: F811
    lead = Lead.objects.for_workspace(workspace).create(workspace=workspace, name="Manual")
    assert client.post(url(workspace, lead), {}, format="json").status_code == 400
    inbound(channel, "hello")
    talking = Lead.objects.for_workspace(workspace).exclude(pk=lead.pk).get()
    # No AI configuration saved yet.
    assert client.post(url(workspace, talking), {}, format="json").status_code == 400


def test_bad_model_output_is_not_saved(client, workspace, channel, config):  # noqa: F811
    inbound(channel, "hello")
    lead = Lead.objects.for_workspace(workspace).get()
    model = Mock()
    model.complete.return_value = Completion("   ", [], 5, 0)
    with patch("apps.agents.providers.provider_for", return_value=model):
        assert client.post(url(workspace, lead), {}, format="json").status_code == 400
    lead.refresh_from_db()
    assert lead.ai_summary == ""


def test_summary_cannot_be_set_through_contact_edits(client, workspace, channel):  # noqa: F811
    inbound(channel, "hello")
    lead = Lead.objects.for_workspace(workspace).get()
    client.patch(
        f"/api/workspaces/{workspace.pk}/leads/{lead.pk}/", {"ai_summary": "forged"}, format="json"
    )
    lead.refresh_from_db()
    assert lead.ai_summary == ""

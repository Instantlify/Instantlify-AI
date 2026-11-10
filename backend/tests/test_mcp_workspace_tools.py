"""Workspace-management MCP tools."""

import pytest

from apps.agents.models import KnowledgeBase, KnowledgeDocument
from apps.automations.models import Automation
from apps.crm.models import Lead
from apps.tools.models import DeepLink
from tests.conftest import set_limits
from tests.test_mcp_connector import call, key_for, quiet_notify  # noqa: F401

pytestmark = pytest.mark.django_db


def test_automations_can_be_listed_and_toggled(workspace):
    raw = key_for(workspace)
    draft = Automation.objects.for_workspace(workspace).create(workspace=workspace, name="Draft")
    live = Automation.objects.for_workspace(workspace).create(
        workspace=workspace,
        name="Live",
        enabled=True,
        published={"triggers": [{"kind": "dm", "keyword": "price"}]},
    )
    listed = call(raw, "list_automations", {})["structuredContent"]["automations"]
    assert {a["name"]: a["published"] for a in listed} == {"Draft": False, "Live": True}
    assert next(a for a in listed if a["name"] == "Live")["triggers"][0]["match"] == "keyword"

    off = call(raw, "set_automation_enabled", {"automation_id": str(live.pk), "enabled": False})
    assert off["structuredContent"]["enabled"] is False
    refused = call(raw, "set_automation_enabled", {"automation_id": str(draft.pk), "enabled": True})
    assert refused["isError"] is True


def test_leads_can_be_found_and_updated(workspace):
    raw = key_for(workspace)
    lead = Lead.objects.for_workspace(workspace).create(
        workspace=workspace, name="Ada", email="ada@example.com", tags=["old"]
    )
    found = call(raw, "list_leads", {"search": "ada"})["structuredContent"]["leads"]
    assert [item["id"] for item in found] == [str(lead.pk)]
    result = call(
        raw,
        "update_lead",
        {
            "lead_id": str(lead.pk),
            "stage": "qualified",
            "add_tags": ["vip"],
            "remove_tags": ["old"],
            "fields": {"city": "Lahore"},
        },
    )["structuredContent"]
    assert result == {
        "id": str(lead.pk),
        "stage": "qualified",
        "tags": ["vip"],
        "fields": {"city": "Lahore"},
    }
    bad = call(raw, "update_lead", {"lead_id": str(lead.pk), "stage": "nope"})
    assert bad["isError"] is True and "Invalid stage" in bad["content"][0]["text"]
    stages = call(raw, "list_pipeline_stages", {})["structuredContent"]["stages"]
    assert stages[0]["id"] == "new"


def test_tracking_links_and_knowledge(workspace):
    set_limits(workspace, ai_agent_enabled=True)
    raw = key_for(workspace)
    made = call(raw, "create_tracking_link", {"title": "Bio", "target": "https://example.com"})
    assert made["structuredContent"]["path"].startswith("/go/l-")
    assert DeepLink.objects.for_workspace(workspace).count() == 1
    assert call(raw, "create_tracking_link", {"title": "x", "target": "http://x.com"})["isError"]
    links = call(raw, "list_tracking_links", {})["structuredContent"]["links"]
    assert links[0]["title"] == "Bio"

    base = KnowledgeBase.objects.for_workspace(workspace).create(workspace=workspace, name="FAQ")
    added = call(
        raw,
        "add_knowledge_text",
        {"title": "Hours", "text": "Open 9-5", "knowledge_base_id": str(base.pk)},
    )
    assert added["structuredContent"]["status"] == "pending"
    assert KnowledgeDocument.objects.for_workspace(workspace).get().knowledge_base == base
    bases = call(raw, "list_knowledge_bases", {})["structuredContent"]
    assert bases["knowledge_bases"][0]["documents"] == 1


def test_write_tools_need_write_scope(workspace):
    raw = key_for(workspace, scopes=("read",))
    lead = Lead.objects.for_workspace(workspace).create(workspace=workspace, name="A")
    result = call(raw, "update_lead", {"lead_id": str(lead.pk), "stage": "won"})
    assert result["isError"] is True and "write" in result["content"][0]["text"]

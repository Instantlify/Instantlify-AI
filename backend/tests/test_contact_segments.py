import json
from unittest.mock import MagicMock, patch

import pytest

from apps.agents.models import AgentConfig
from apps.agents.providers import Completion
from apps.crm.models import ContactSegment, Lead
from apps.crm.segments import classify_segments
from tests.test_meta_client import connect, inbound

pytestmark = pytest.mark.django_db


def test_named_segments_validate_and_remove_managed_tags_on_rename_and_delete(client, workspace):
    url = f"/api/workspaces/{workspace.pk}/segments/"
    lead = Lead.objects.for_workspace(workspace).create(
        workspace=workspace, name="A", tags=["vip", "segment:Enterprise"]
    )
    response = client.post(
        url, {"name": "Enterprise", "prompt": "Asked for a team demo"}, format="json"
    )
    assert response.status_code == 201, response.content
    item = response.json()
    lead.refresh_from_db()
    assert lead.segment_due_at is not None
    assert (
        client.post(url, {"name": "enterprise", "prompt": "Duplicate"}, format="json").status_code
        == 400
    )
    assert (
        client.post(url, {"name": "Bad:name", "prompt": "Invalid"}, format="json").status_code
        == 400
    )
    detail = url + item["id"] + "/"
    assert client.patch(detail, {"name": "Teams"}, format="json").status_code == 200
    lead.refresh_from_db()
    assert lead.tags == ["vip"]
    lead.tags.append("segment:Teams")
    lead.save()
    assert client.delete(detail).status_code == 204
    lead.refresh_from_db()
    assert lead.tags == ["vip"]


def test_classification_accepts_only_configured_ids_and_preserves_manual_tags(workspace):
    with patch("apps.crm.services.notify"):
        message = inbound(connect(workspace), "Please book an enterprise demo")
    lead = message.conversation.identity.lead
    lead.tags = ["vip"]
    lead.save()
    config = AgentConfig.objects.for_workspace(workspace).create(
        workspace=workspace, enabled=True, is_test=True
    )
    segment = ContactSegment.objects.for_workspace(workspace).create(
        workspace=workspace, name="Enterprise", prompt="Requests an enterprise demo"
    )
    provider = MagicMock()
    provider.complete.return_value = Completion(json.dumps([str(segment.pk)]), [], 5, 2)
    with patch("apps.agents.providers.provider_for", return_value=provider):
        classify_segments(config, lead, [message])
        classify_segments(config, lead, [message])
    provider.complete.assert_called_once()
    lead.refresh_from_db()
    assert lead.tags == ["vip", "segment:Enterprise"]


def test_unknown_segment_output_never_changes_tags(workspace):
    with patch("apps.crm.services.notify"):
        message = inbound(connect(workspace), "Hello")
    lead = message.conversation.identity.lead
    lead.tags = ["vip"]
    lead.save()
    config = AgentConfig.objects.for_workspace(workspace).create(
        workspace=workspace, enabled=True, is_test=True
    )
    ContactSegment.objects.for_workspace(workspace).create(
        workspace=workspace, name="Enterprise", prompt="Enterprise"
    )
    provider = MagicMock()
    provider.complete.return_value = Completion('["unconfigured-id"]', [], 5, 2)
    with patch("apps.agents.providers.provider_for", return_value=provider):
        classify_segments(config, lead, [message])
    lead.refresh_from_db()
    assert lead.tags == ["vip"]


def test_plan_downgrade_blocks_segment_creation_and_manual_contact_cap(client, workspace):
    from tests.conftest import set_limits

    set_limits(workspace, ai_agent_enabled=False, max_contacts=0)
    response = client.post(
        f"/api/workspaces/{workspace.pk}/segments/",
        {"name": "Blocked", "prompt": "Enterprise"},
        format="json",
    )
    assert response.status_code == 402
    assert not ContactSegment.objects.for_workspace(workspace).exists()
    response = client.post(
        f"/api/workspaces/{workspace.pk}/leads/",
        {"name": "Too many", "email": "a@example.com"},
        format="json",
    )
    assert response.status_code == 402
    assert not Lead.objects.for_workspace(workspace).exists()


def test_inbound_contact_cap_defers_event_without_losing_it(workspace):
    from django.utils import timezone

    from apps.channels.models import WebhookEvent
    from apps.channels.tasks import process_webhook
    from tests.conftest import set_limits

    channel = connect(workspace)
    set_limits(workspace, max_contacts=0)
    event = WebhookEvent.objects.for_workspace(workspace).create(
        workspace=workspace,
        connection=channel,
        event_id="capped-contact",
        payload=json.dumps({"sender_id": "new-contact", "text": "Hello", "kind": "dm"}),
        available_at=timezone.now(),
    )
    with patch("apps.crm.services.notify"):
        process_webhook(str(workspace.pk), str(event.pk))
    event.refresh_from_db()
    assert (event.status, event.attempts, event.error_code) == ("pending", 0, "plan_contact_limit")
    assert not Lead.objects.for_workspace(workspace).exists()
    set_limits(workspace, max_contacts=1)
    event.available_at = timezone.now()
    event.save()
    with patch("apps.crm.services.notify"):
        process_webhook(str(workspace.pk), str(event.pk))
    event.refresh_from_db()
    assert event.status == "processed"
    assert Lead.objects.for_workspace(workspace).count() == 1

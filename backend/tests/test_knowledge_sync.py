from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.agents.models import KnowledgeDocument, KnowledgeSourceSync
from apps.agents.sync import dispatch_source_syncs, refresh_source
from apps.crm.models import IntegrationConfig
from tests.conftest import set_limits
from tests.test_knowledge_sources import config

pytestmark = pytest.mark.django_db


def scheduled(workspace):
    source = config(workspace, "google_sheets", spreadsheet_id="sheet")
    row = KnowledgeSourceSync.objects.for_workspace(workspace).create(
        workspace=workspace, integration=source, enabled=True, next_run_at=timezone.now()
    )
    return source, row


def due(row):
    row.next_run_at = timezone.now() - timedelta(seconds=1)
    row.save()


def test_schedule_is_opt_in_validated_and_can_be_paused_after_downgrade(client, workspace):
    source = config(workspace, "google_sheets", spreadsheet_id="sheet")
    url = f"/api/workspaces/{workspace.pk}/integrations/{source.pk}/knowledge/schedule/"
    assert client.get(url).json()["enabled"] is False
    assert not KnowledgeSourceSync.objects.for_workspace(workspace).exists()
    assert (
        client.put(url, {"enabled": True, "interval_minutes": 1}, format="json").status_code == 400
    )
    response = client.put(url, {"enabled": True, "interval_minutes": 360}, format="json")
    assert response.status_code == 200, response.content
    assert response.json()["next_run_at"]
    set_limits(workspace, ai_agent_enabled=False)
    assert client.put(url, {"enabled": True}, format="json").status_code == 402
    assert client.put(url, {"enabled": False}, format="json").status_code == 200
    row = KnowledgeSourceSync.objects.for_workspace(workspace).get()
    assert not row.enabled and row.next_run_at is None


def test_refresh_updates_one_document_and_unchanged_content_does_not_reindex(workspace):
    _, row = scheduled(workspace)
    with patch("apps.agents.sync.source_text", return_value="First answer") as fetch:
        refresh_source(str(workspace.pk), str(row.pk))
        # A duplicate queue message cannot repeat a completed refresh before it is due.
        refresh_source(str(workspace.pk), str(row.pk))
    assert fetch.call_count == 1
    document = KnowledgeDocument.objects.for_workspace(workspace).get()
    document.status = "ready"
    document.save()
    row.refresh_from_db()
    assert row.status == "synced" and row.last_success_at
    due(row)
    with patch("apps.agents.sync.source_text", return_value="First answer"):
        refresh_source(str(workspace.pk), str(row.pk))
    document.refresh_from_db()
    assert document.status == "ready" and document.source_revision == 0
    row.refresh_from_db()
    due(row)
    with patch("apps.agents.sync.source_text", return_value="Changed answer"):
        refresh_source(str(workspace.pk), str(row.pk))
    document.refresh_from_db()
    assert document.source_revision == 1 and document.source == "Changed answer"
    assert document.status == "pending"
    assert KnowledgeDocument.objects.for_workspace(workspace).count() == 1


def test_fetch_failure_preserves_knowledge_and_does_not_expose_provider_error(workspace):
    source, row = scheduled(workspace)
    document = KnowledgeDocument.objects.for_workspace(workspace).create(
        workspace=workspace,
        title=f"Connected source: {source.provider} ({source.pk})",
        source="Keep this",
    )
    with patch(
        "apps.agents.sync.source_text", side_effect=ValueError("private-key-in-provider-body")
    ):
        refresh_source(str(workspace.pk), str(row.pk))
    document.refresh_from_db()
    row.refresh_from_db()
    assert document.source == "Keep this"
    assert row.status == "error" and row.error_code == "source_fetch_failed"
    assert row.next_run_at > timezone.now() and row.last_success_at is None


def test_disabling_during_fetch_discards_the_in_flight_result(client, workspace):
    source, row = scheduled(workspace)
    url = f"/api/workspaces/{workspace.pk}/integrations/{source.pk}/knowledge/schedule/"

    def disable(_config):
        assert client.put(url, {"enabled": False}, format="json").status_code == 200
        return "Do not apply this"

    with patch("apps.agents.sync.source_text", side_effect=disable):
        refresh_source(str(workspace.pk), str(row.pk))
    assert not KnowledgeDocument.objects.for_workspace(workspace).exists()
    row.refresh_from_db()
    assert not row.enabled and row.status == "idle"


def test_changed_destination_during_fetch_discards_the_old_source(workspace):
    source, row = scheduled(workspace)

    def change_destination(_config):
        IntegrationConfig.objects.for_workspace(workspace).filter(pk=source.pk).update(
            options={"spreadsheet_id": "different-sheet"}
        )
        return "Old destination"

    with patch("apps.agents.sync.source_text", side_effect=change_destination):
        refresh_source(str(workspace.pk), str(row.pk))
    assert not KnowledgeDocument.objects.for_workspace(workspace).exists()
    row.refresh_from_db()
    assert row.status == "error"


def test_worker_rechecks_plan_before_contacting_provider(workspace):
    _, row = scheduled(workspace)
    set_limits(workspace, ai_agent_enabled=False)
    with patch("apps.agents.sync.source_text") as fetch:
        refresh_source(str(workspace.pk), str(row.pk))
    fetch.assert_not_called()
    row.refresh_from_db()
    assert row.error_code == "plan_limit"


def test_dispatch_recovers_an_interrupted_lease(workspace):
    _, row = scheduled(workspace)
    row.status = "running"
    row.started_at = timezone.now() - timedelta(minutes=11)
    row.save()
    with patch("apps.agents.sync.enqueue_once") as enqueue:
        dispatch_source_syncs()
    enqueue.assert_called_once()
    row.refresh_from_db()
    assert row.status == "error" and row.error_code == "worker_interrupted"


def test_cross_workspace_schedule_is_hidden(client, workspace, user):
    from apps.tenants.services import create_workspace

    other = create_workspace(user, "Other source owner")
    source = config(other, "google_sheets", spreadsheet_id="other-sheet")
    url = f"/api/workspaces/{workspace.pk}/integrations/{source.pk}/knowledge/schedule/"
    assert client.get(url).status_code == 404
    assert client.put(url, {"enabled": True}, format="json").status_code == 404

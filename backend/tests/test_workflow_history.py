# ruff: noqa: F811 -- imported pytest fixtures are injected by parameter name.
from datetime import timedelta
from importlib import import_module
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.db import connection
from django.utils import timezone

from apps.automations.models import AutomationExecution, ConversationState
from apps.automations.services import start_flow
from apps.channels.models import Delivery
from tests.test_guided_automation import (  # noqa: F401
    channel,
    flow,
    inbound,
    publish,
    quiet_notify,
    run,
)

pytestmark = pytest.mark.django_db


def test_history_survives_next_run_and_excludes_customer_text(client, workspace, channel):  # noqa: F811
    graph = flow()
    assert publish(client, workspace, graph).status_code == 200
    message = inbound(channel, "guide", kind="comment")
    state = ConversationState.objects.for_workspace(workspace).get()
    run(state)
    first = AutomationExecution.objects.for_workspace(workspace).get()
    assert first.status == "completed" and first.finished_at
    assert first.trace[-1]["status"] == "completed"
    assert "guide" not in str(first.trace)
    state.cooldown_until = timezone.now() - timedelta(seconds=1)
    state.save()
    start_flow(state.conversation, state.automation, message=message)
    rows = client.get(
        f"/api/workspaces/{workspace.pk}/automation-runs/?automation={state.automation_id}"
    ).json()
    assert len(rows) == 2
    assert rows[0]["status"] == "running" and rows[1]["status"] == "completed"
    assert first.pk != rows[0]["id"]


def test_walkthrough_does_not_create_a_run_or_send_messages(client, workspace):
    graph = flow()
    response = client.post(
        f"/api/workspaces/{workspace.pk}/automations/preview/", {"graph": graph}, format="json"
    )
    assert response.status_code == 200, response.content
    assert response.json()["trace"][-1]["kind"] == "end"
    assert not response.json()["side_effects"]
    assert not ConversationState.objects.for_workspace(workspace).exists()
    assert not AutomationExecution.objects.for_workspace(workspace).exists()
    assert not Delivery.objects.for_workspace(workspace).exists()


def test_legacy_backfill_gives_distinct_runs_to_existing_conversations(client, workspace, channel):
    assert publish(client, workspace, flow()).status_code == 200
    inbound(channel, "guide", kind="comment", sender_id="first")
    inbound(channel, "guide", kind="comment", sender_id="second")
    states = ConversationState.objects.for_workspace(workspace)
    assert states.count() == 2
    shared_token = states.first().run_token
    states.update(run_token=shared_token)
    AutomationExecution.objects.for_workspace(workspace).delete()
    migration = import_module("apps.automations.migrations.0008_automationexecution")
    migration.backfill(apps, SimpleNamespace(connection=connection))
    assert AutomationExecution.objects.for_workspace(workspace).count() == 2
    assert len(set(states.values_list("run_token", flat=True))) == 2


def test_walkthrough_uses_the_real_saved_variable_names_for_branching(client, workspace):
    graph = {
        "start": "generate",
        "triggers": [{"kind": "dm", "keyword": "hello", "channel": "instagram"}],
        "nodes": [
            {
                "id": "generate",
                "data": {"kind": "ai_generate", "prompt": "Return yes", "variable": "decision"},
            },
            {"id": "check", "data": {"kind": "condition", "variable": "decision", "equals": "yes"}},
            {"id": "yes", "data": {"kind": "end"}},
            {"id": "no", "data": {"kind": "end"}},
        ],
        "edges": [
            {"source": "generate", "target": "check"},
            {"source": "check", "target": "yes", "sourceHandle": "true"},
            {"source": "check", "target": "no", "sourceHandle": "false"},
        ],
    }
    response = client.post(
        f"/api/workspaces/{workspace.pk}/automations/preview/",
        {"graph": graph, "samples": {"generate": "yes"}},
        format="json",
    )
    assert response.status_code == 200, response.content
    assert [row["node_id"] for row in response.json()["trace"]] == ["generate", "check", "yes"]
    assert not AutomationExecution.objects.for_workspace(workspace).exists()

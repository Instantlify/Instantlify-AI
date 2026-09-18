"""Admin automations (2.5.8): Copy, Transfer and per-automation History."""

import time
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test import Client
from django.utils import timezone

from apps.automations.models import (
    Automation,
    AutomationTransferLog,
    Edge,
    Node,
    Trigger,
)
from apps.automations.services import duplicate, publish, transfer
from apps.channels.models import ChannelConnection
from apps.platform_ops.models import PlatformAudit, PlatformRole
from apps.platform_ops.security import new_secret
from apps.tenants.models import User
from apps.tenants.services import create_workspace

pytestmark = pytest.mark.django_db

GRAPH = {
    "start": "hello",
    "triggers": [{"kind": "comment", "keyword": "price"}],
    "nodes": [
        {"id": "hello", "data": {"kind": "send_message", "text": "Hi"}},
        {"id": "done", "data": {"kind": "end"}},
    ],
    "edges": [{"source": "hello", "target": "done"}],
}


@pytest.fixture(autouse=True)
def console_host(settings):
    settings.ALLOWED_HOSTS = [*settings.ALLOWED_HOSTS, "ops.localhost"]


def staff():
    person = User.objects.create_user(
        username="ops", email="ops@example.com", password="A-very-long-password42", is_staff=True
    )
    return PlatformRole.objects.create(
        user=person, role="owner", otp_secret=new_secret(), otp_confirmed=True
    )


def console(operator):
    client = Client(HTTP_HOST="ops.localhost")
    client.force_login(operator.user)
    session = client.session
    session["platform_password_at"] = time.time()
    session["platform_mfa"] = {"version": operator.version, "until": time.time() + 1800}
    session.save()
    return client


def published(workspace, user):
    automation = Automation.objects.for_workspace(workspace).create(
        workspace=workspace, name="Price reply"
    )
    publish(automation, GRAPH, user)
    automation.refresh_from_db()
    return automation


def connect(workspace, handle):
    return ChannelConnection.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider="instagram",
        external_account_id=f"ig-{handle}",
        display_name=handle,
        access_token="x",
        expires_at=timezone.now() + timedelta(days=30),
    )


def test_copy_is_an_identical_independent_disabled_draft(workspace, user):
    source = published(workspace, user)
    target = create_workspace(user, "Client")
    copy = duplicate(source, target, user)
    assert copy.workspace_id == target.pk and not copy.enabled
    assert copy.draft["nodes"] == (source.published or source.draft)["nodes"]
    # Editing the copy never reaches the original.
    copy.draft["nodes"][0]["data"]["text"] = "Changed"
    copy.save()
    source.refresh_from_db()
    assert (source.published or source.draft)["nodes"][0]["data"]["text"] == "Hi"


def test_transfer_moves_every_row_and_leaves_nothing_behind(workspace, user):
    source = published(workspace, user)
    target = create_workspace(user, "Client")
    before = {
        model: model.all_objects.filter(automation=source).count()
        for model in (Trigger, Node, Edge)
    }
    assert before[Node] == 2
    transfer(source, target, operator=user, reason="Client changed account")
    for model in (Trigger, Node, Edge):
        assert not model.all_objects.filter(automation=source, workspace=workspace).exists()
        assert (
            model.all_objects.filter(automation=source, workspace=target).count() == before[model]
        )
    source.refresh_from_db()
    assert source.workspace_id == target.pk and not source.enabled
    log = AutomationTransferLog.objects.get()
    assert log.from_workspace_id == workspace.pk and log.to_workspace_id == target.pk


def test_transfer_needs_a_reason_and_a_different_workspace(workspace, user):
    source = published(workspace, user)
    with pytest.raises(ValueError):
        transfer(source, create_workspace(user, "Client"), operator=user, reason=" ")
    with pytest.raises(ValueError):
        transfer(source, workspace, operator=user, reason="No-op")


def test_console_copy_and_transfer_are_audited(workspace, user):
    source = published(workspace, user)
    client_workspace = create_workspace(user, "Client")
    target = connect(client_workspace, "client_handle")
    connect(workspace, "own_handle")
    client = console(staff())

    assert (
        client.post(f"/ops/automations/{source.pk}/copy/", {"target": target.pk}).status_code == 302
    )
    assert Automation.all_objects.filter(
        workspace=client_workspace, name="Price reply (copy)"
    ).exists()
    assert (
        client.post(f"/ops/automations/{source.pk}/transfer/", {"target": target.pk}).status_code
        == 403
    )
    assert (
        client.post(
            f"/ops/automations/{source.pk}/transfer/", {"target": target.pk, "reason": "Moved"}
        ).status_code
        == 302
    )
    actions = set(PlatformAudit.objects.values_list("action", flat=True))
    assert {"automation.copied", "automation.transferred"} <= actions


def test_history_lists_this_automations_runs(workspace, user):
    source = published(workspace, user)
    connection = connect(workspace, "own_handle")
    client = console(staff())
    with patch("redis.Redis.get", return_value=None), patch("redis.Redis.ttl", return_value=-2):
        page = client.get(f"/ops/?tab=automations&sub={connection.pk}&runs={source.pk}")
    assert page.status_code == 200
    assert b"Run history" in page.content and b"has not run yet" in page.content

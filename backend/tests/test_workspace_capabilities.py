import time
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test import Client
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

from apps.channels.instagram import LiveInstagramAdapter
from apps.channels.transport import ProviderError
from apps.content.models import ScheduledPost
from apps.content.tasks import publish_post
from apps.platform_ops.capabilities import capabilities_for, check_capability, has_capability
from apps.platform_ops.models import PlatformAudit, PlatformRole, WorkspaceCapability
from apps.platform_ops.security import new_secret
from apps.tenants.models import Membership, User
from apps.tenants.services import create_workspace
from apps.tools.creator_metrics import refresh_creator_metrics
from apps.tools.models import CreatorKit
from tests.test_creator_metrics import connection

pytestmark = pytest.mark.django_db


def grant(workspace, key="meta_analytics"):
    return WorkspaceCapability.objects.create(
        workspace=workspace, key=key, enabled=True, reason="Approved for testing"
    )


def test_default_denial_and_workspace_isolation(workspace, user):
    other = create_workspace(user, "Other")
    assert capabilities_for(workspace.pk) == {"meta_analytics": False, "meta_publishing": False}
    with pytest.raises(PermissionDenied):
        check_capability(workspace.pk, "meta_analytics")
    grant(workspace)
    assert has_capability(workspace.pk, "meta_analytics")
    assert not has_capability(other.pk, "meta_analytics")
    assert not has_capability(workspace.pk, "meta_publishing")
    with pytest.raises(ValueError):
        check_capability(workspace.pk, "unknown")


def test_members_can_read_but_cannot_self_grant(client, workspace):
    member = User.objects.create_user(username="teammate", email="team@example.com")
    Membership.objects.for_workspace(workspace).create(
        workspace=workspace, user=member, role="agent"
    )
    teammate = APIClient()
    teammate.force_authenticate(member)
    url = f"/api/workspaces/{workspace.pk}/status/"
    grant(workspace)
    assert client.get(url).json()["capabilities"]["meta_analytics"] is True
    assert teammate.get(url).json()["capabilities"]["meta_analytics"] is True
    assert teammate.get(url).json()["capabilities"]["meta_publishing"] is False
    assert (
        teammate.patch(url, {"capabilities": {"meta_publishing": True}}, format="json").status_code
        == 405
    )
    assert not has_capability(workspace.pk, "meta_publishing")


def test_foreign_workspace_status_is_hidden(client, user):
    other_user = User.objects.create_user(username="outsider", email="other@example.com")
    other = create_workspace(other_user, "Private")
    grant(other)
    assert client.get(f"/api/workspaces/{other.pk}/status/").status_code == 404


@pytest.fixture
def console(user, settings):
    settings.ALLOWED_HOSTS = [*settings.ALLOWED_HOSTS, "ops.localhost"]
    user.is_staff = True
    user.save()
    role = PlatformRole.objects.create(
        user=user, role="owner", otp_secret=new_secret(), otp_confirmed=True
    )
    client = Client(HTTP_HOST="ops.localhost")
    client.force_login(user)
    session = client.session
    session["platform_mfa"] = {"version": role.version, "until": time.time() + 1800}
    session.save()
    return client, role


def test_console_grants_revokes_and_audits(console, workspace):
    client, _ = console
    body = {
        "workspace": str(workspace.pk),
        "key": "meta_analytics",
        "enabled": "true",
        "reason": "Pilot customer",
    }
    assert client.post("/ops/capabilities/", body).status_code == 302
    assert has_capability(workspace.pk, "meta_analytics")
    assert client.post("/ops/capabilities/", {**body, "enabled": "false"}).status_code == 302
    assert not has_capability(workspace.pk, "meta_analytics")
    logs = PlatformAudit.objects.filter(action="capability.changed", workspace_id=str(workspace.pk))
    assert logs.count() == 2
    assert logs.first().detail["enabled"] is False
    response = client.get(f"/ops/?tab=operations&q={workspace.pk}")
    assert response.status_code == 200
    assert b"Advanced Meta access by workspace" in response.content
    assert b"Grant access" in response.content


@pytest.mark.parametrize("role_name", ["support", "analyst"])
def test_console_requires_platform_owner(console, workspace, role_name):
    client, role = console
    role.role = role_name
    role.save()
    assert (
        client.post(
            "/ops/capabilities/",
            {
                "workspace": str(workspace.pk),
                "key": "meta_analytics",
                "enabled": "true",
                "reason": "Test",
            },
        ).status_code
        == 403
    )
    assert not has_capability(workspace.pk, "meta_analytics")


@pytest.mark.parametrize("changes", [{"reason": ""}, {"enabled": "yes"}, {"key": "unknown"}])
def test_console_rejects_invalid_changes(console, workspace, changes):
    client, _ = console
    body = {
        "workspace": str(workspace.pk),
        "key": "meta_analytics",
        "enabled": "true",
        "reason": "Test",
    }
    assert client.post("/ops/capabilities/", {**body, **changes}).status_code == 403
    assert not WorkspaceCapability.objects.exists()


def test_analytics_api_and_worker_blocked_then_revoked(client, workspace):
    channel = connection(workspace)
    url = f"/api/workspaces/{workspace.pk}/creator-kit/"
    body = {
        "slug": "restricted",
        "name": "Creator",
        "published": True,
        "live_connection_ids": [str(channel.pk)],
    }
    response = client.put(url, body, format="json")
    assert response.status_code == 403
    assert response.json()["code"] == "capability_approval_required"
    approval = grant(workspace)
    assert client.put(url, body, format="json").status_code == 200
    kit = CreatorKit.objects.for_workspace(workspace).get()
    approval.enabled = False
    approval.save()
    with patch("apps.tools.creator_metrics.request") as fetch:
        refresh_creator_metrics(str(workspace.pk), str(kit.pk))
    fetch.assert_not_called()
    kit.refresh_from_db()
    assert kit.live_stats_error == "capability_approval_required"
    assert client.get("/api/public/creator/restricted/").json()["live_statistics"] == []
    assert client.put(url, {**body, "live_connection_ids": []}, format="json").status_code == 200


def test_revocation_during_analytics_fetch_discards_result(client, workspace):
    channel = connection(workspace)
    approval = grant(workspace)
    kit = CreatorKit.objects.for_workspace(workspace).create(
        workspace=workspace,
        slug="inflight",
        name="Creator",
        live_connection_ids=[str(channel.pk)],
        live_stats_next_at=timezone.now(),
    )

    def revoke(*args, **kwargs):
        approval.enabled = False
        approval.save()
        return {"followers_count": 999}

    with patch("apps.tools.creator_metrics.request", side_effect=revoke):
        refresh_creator_metrics(str(workspace.pk), str(kit.pk))
    channel.refresh_from_db()
    assert channel.profile["followers_count"] == 120


def test_publishing_api_and_queued_work_require_approval(client, workspace):
    channel = connection(workspace)
    url = f"/api/workspaces/{workspace.pk}/posts/"
    body = {
        "connection": str(channel.pk),
        "media_url": "https://example.com/photo.jpg",
        "scheduled_at": (timezone.now() + timedelta(hours=1)).isoformat(),
    }
    assert client.post(url, body, format="json").status_code == 403
    approval = grant(workspace, "meta_publishing")
    response = client.post(url, body, format="json")
    assert response.status_code == 201
    post = ScheduledPost.objects.for_workspace(workspace).get(pk=response.json()["id"])
    approval.enabled = False
    approval.save()
    assert (
        client.patch(f"{url}{post.pk}/", {"caption": "Blocked"}, format="json").status_code == 403
    )
    post.scheduled_at = timezone.now()
    post.save()
    with patch("apps.content.tasks.adapter_for") as adapter:
        publish_post(str(workspace.pk), str(post.pk))
    adapter.assert_not_called()
    post.refresh_from_db()
    assert post.error_code == "capability_approval_required"
    assert client.delete(f"{url}{post.pk}/").status_code == 204


def test_direct_provider_publishing_cannot_bypass_approval(workspace):
    adapter = LiveInstagramAdapter(connection(workspace))
    with patch("apps.channels.instagram.request") as request:
        with pytest.raises(ProviderError, match="capability_approval_required"):
            adapter.publish_container("container")
    request.assert_not_called()


def test_basic_dm_and_comment_replies_do_not_require_advanced_approval(workspace):
    adapter = LiveInstagramAdapter(connection(workspace))
    with patch(
        "apps.channels.instagram.request", return_value={"message_id": "reply-1"}
    ) as request:
        assert (
            adapter.send_message(recipient_id="user-1", text="Hello", idempotency_key="dm")
            == "reply-1"
        )
        assert (
            adapter.send_message(
                recipient_id="comment-1",
                text="Hello",
                idempotency_key="comment",
                private_reply=True,
            )
            == "reply-1"
        )
    assert request.call_count == 2


def test_console_requires_mfa(console, workspace):
    client, _ = console
    session = client.session
    session.pop("platform_mfa")
    session.save()
    response = client.post(
        "/ops/capabilities/",
        {
            "workspace": str(workspace.pk),
            "key": "meta_analytics",
            "enabled": "true",
            "reason": "Test",
        },
    )
    assert response.url == "/ops/mfa/"
    assert not WorkspaceCapability.objects.exists()

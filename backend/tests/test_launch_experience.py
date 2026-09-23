"""Launch regressions: account recovery, safe previews and honest funnel metrics."""

import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from conftest import set_limits
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.agents.models import AgentConfig, ToolCall, UsageRecord
from apps.agents.providers import Completion
from apps.analytics.models import FunnelEvent
from apps.analytics.services import funnel, record
from apps.channels.transport import ProviderError
from apps.crm.models import Conversation, Message
from apps.tenants.models import Membership, User

pytestmark = pytest.mark.django_db


def reset_body(user, password="New-river-saffron-cloud42"):
    return {
        "uid": urlsafe_base64_encode(force_bytes(user.pk)),
        "token": default_token_generator.make_token(user),
        "password": password,
    }


def test_reset_request_does_not_disclose_account_and_emails_fragment(user):
    client = APIClient()
    known = client.post("/api/auth/password-reset/", {"email": user.email})
    unknown = client.post("/api/auth/password-reset/", {"email": "missing@example.com"})
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert len(mail.outbox) == 1
    assert "/auth/reset/#uid=" in mail.outbox[0].body


def test_reset_is_single_use_and_revokes_refresh_tokens(user):
    token = RefreshToken.for_user(user)
    client = APIClient()
    body = reset_body(user)
    assert client.post("/api/auth/password-reset/confirm/", body).status_code == 200
    user.refresh_from_db()
    assert user.check_password(body["password"])
    assert client.post("/api/auth/password-reset/confirm/", body).status_code == 400
    assert client.post("/api/auth/token/refresh/", {"refresh": str(token)}).status_code == 401


def test_reset_rejects_expired_and_weak_passwords(user, settings):
    client = APIClient()
    assert (
        client.post("/api/auth/password-reset/confirm/", reset_body(user, "short")).status_code
        == 400
    )
    body = reset_body(user)
    settings.PASSWORD_RESET_TIMEOUT = -1
    assert client.post("/api/auth/password-reset/confirm/", body).status_code == 400


@pytest.mark.parametrize(
    "uid", ["bad", "aW52YWxpZA", "OTk5OTk5OTk5OTk5OTk5OTk5OTk5OTk5OTk5OTk5OTk5"]
)
def test_reset_malformed_user_ids_are_not_server_errors(uid):
    response = APIClient().post(
        "/api/auth/password-reset/confirm/",
        {
            "uid": uid,
            "token": "bad",
            "password": "New-river-saffron-cloud42",
        },
    )
    assert response.status_code == 400


def test_recovery_requires_csrf(user):
    client = APIClient(enforce_csrf_checks=True)
    assert client.post("/api/auth/password-reset/", {"email": user.email}).status_code == 403
    assert client.post("/api/auth/password-reset/confirm/", reset_body(user)).status_code == 403


def test_banned_user_cannot_recover(user):
    body = reset_body(user)
    user.is_banned = True
    user.save()
    client = APIClient()
    assert client.post("/api/auth/password-reset/confirm/", body).status_code == 400
    assert client.post("/api/auth/password-reset/", {"email": user.email}).status_code == 200
    assert len(mail.outbox) == 0


def preview_config(workspace):
    set_limits(workspace)
    return AgentConfig.objects.for_workspace(workspace).create(workspace=workspace, is_test=True)


def test_preview_never_creates_messages_conversations_or_tools(client, workspace):
    preview_config(workspace)
    chunk = SimpleNamespace(
        text="Consultation costs $49.", document=SimpleNamespace(title="Services")
    )
    with (
        patch("apps.agents.preview.retrieve", return_value=[chunk]),
        patch("apps.agents.preview.provider_for") as provider,
    ):
        provider.return_value.complete.return_value = Completion(
            "It costs $49.", [{"name": "book"}], 10, 5
        )
        response = client.post(
            f"/api/workspaces/{workspace.pk}/agent/preview/", {"question": "Price?"}
        )
    assert response.status_code == 200
    assert response.json()["sources"] == ["Services"]
    assert provider.return_value.complete.call_args.args[1] == []
    assert not Message.all_objects.exists()
    assert not Conversation.all_objects.exists()
    assert not ToolCall.all_objects.exists()
    usage = UsageRecord.objects.for_workspace(workspace).get(kind="preview")
    assert usage.status == "complete" and usage.input_tokens == 10


def test_preview_handoff_does_not_call_provider(client, workspace):
    preview_config(workspace)
    with patch("apps.agents.preview.provider_for") as provider:
        response = client.post(
            f"/api/workspaces/{workspace.pk}/agent/preview/", {"question": "I want a human"}
        )
    assert response.json()["handoff"] is True
    provider.assert_not_called()
    assert not Conversation.all_objects.exists()


def test_preview_permissions_and_validation(client, workspace):
    preview_config(workspace)
    url = f"/api/workspaces/{workspace.pk}/agent/preview/"
    assert client.post(url, {"question": " "}).status_code == 400
    assert client.post(url, {"question": "x" * 2001}).status_code == 400
    stranger = User.objects.create_user(username="stranger", email="stranger@example.com")
    other = APIClient()
    other.force_authenticate(stranger)
    assert other.post(url, {"question": "Price?"}).status_code == 404
    Membership.objects.for_workspace(workspace).create(
        workspace=workspace, user=stranger, role="agent"
    )
    assert other.post(url, {"question": "Price?"}).status_code == 403


def test_preview_checks_credit_before_retrieval(client, workspace):
    config = preview_config(workspace)
    config.is_test = False
    config.save()
    with (
        patch("apps.billing.credits.ensure_credit", return_value=False),
        patch("apps.agents.preview.retrieve") as retrieve,
    ):
        response = client.post(
            f"/api/workspaces/{workspace.pk}/agent/preview/", {"question": "Price?"}
        )
    assert response.status_code == 403
    retrieve.assert_not_called()


def test_preview_provider_failure_is_safe(client, workspace):
    preview_config(workspace)
    with patch("apps.agents.preview.retrieve", side_effect=ProviderError("secret-provider-detail")):
        response = client.post(
            f"/api/workspaces/{workspace.pk}/agent/preview/", {"question": "Price?"}
        )
    assert response.status_code == 503
    assert "secret-provider-detail" not in str(response.content)
    assert UsageRecord.objects.for_workspace(workspace).get().status == "failed"


def test_funnel_deduplicates_entry_and_excludes_unrelated_or_reversed_conversions(workspace):
    lead, unrelated = uuid.uuid4(), uuid.uuid4()
    record(workspace.pk, "comment", lead_id=lead)
    record(workspace.pk, "dm", lead_id=lead)
    record(workspace.pk, "replied", lead_id=lead)
    record(workspace.pk, "booked", lead_id=unrelated)
    early = record(workspace.pk, "booked", lead_id=lead)
    FunnelEvent.objects.for_workspace(workspace).filter(pk=early.pk).update(
        created_at=timezone.now() - timedelta(hours=1)
    )
    data = funnel(workspace.pk)
    assert data["unique_leads"] == 1
    steps = {item["kind"]: item for item in data["steps"]}
    assert steps["dm"]["conversion"] is None
    assert steps["booked"]["leads"] == 2
    assert steps["booked"]["conversion"] == 0
    record(workspace.pk, "booked", lead_id=lead)
    steps = {item["kind"]: item for item in funnel(workspace.pk)["steps"]}
    assert steps["booked"]["conversion"] == 1

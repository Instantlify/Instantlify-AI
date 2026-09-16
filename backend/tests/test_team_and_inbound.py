"""Team invitations/seat limits, voice-note transcription and AI lead segmentation."""

import json
from datetime import timedelta
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.agents.models import AgentConfig, UsageRecord
from apps.agents.providers import Completion
from apps.automations.models import Automation, ConversationState
from apps.automations.services import publish
from apps.billing.services import account_for
from apps.channels.models import ChannelConnection, WebhookEvent
from apps.crm.models import Conversation, IntegrationConfig, IntegrationJob, Lead, Message
from apps.crm.services import receive
from apps.crm.tasks import dispatch_inbound_jobs, segment_lead, transcribe_message
from apps.tenants.models import Invitation, Membership, User
from apps.tenants.services import create_workspace

pytestmark = pytest.mark.django_db


def as_user(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def seats(workspace, count):
    account = account_for(workspace.pk)
    account.seat_limit = count
    account.save()


def invite(client, workspace, email, role="agent"):
    return client.post(
        f"/api/workspaces/{workspace.pk}/invitations/", {"email": email, "role": role}
    )


def token_from(response):
    return parse_qs(urlparse(response.json()["accept_url"]).query)["invite"][0]


def new_user(email):
    return User.objects.create_user(username=email, email=email, password="A-very-long-pass42")


def test_invite_accept_flow_respects_email_and_single_use(client, workspace):
    seats(workspace, 3)
    response = invite(client, workspace, "  Teammate@Example.com ")
    assert response.status_code == 201
    token = token_from(response)
    stored = Invitation.objects.for_workspace(workspace).get()
    assert stored.email == "teammate@example.com"
    assert token not in stored.token_hash
    listed = client.get(f"/api/workspaces/{workspace.pk}/invitations/").content.decode()
    assert "token" not in listed and stored.token_hash not in listed

    stranger = new_user("stranger@example.com")
    rejected = as_user(stranger).post("/api/invitations/accept/", {"token": token})
    assert rejected.status_code == 400

    teammate = new_user("TEAMMATE@example.com")
    accepted = as_user(teammate).post("/api/invitations/accept/", {"token": token})
    assert accepted.status_code == 201
    assert Membership.objects.for_workspace(workspace).get(user=teammate).role == "agent"
    assert as_user(teammate).post("/api/invitations/accept/", {"token": token}).status_code == 400


def test_seat_limit_counts_members_and_open_invitations(client, workspace):
    seats(workspace, 1)
    assert invite(client, workspace, "a@example.com").status_code == 400
    seats(workspace, 2)
    assert invite(client, workspace, "a@example.com").status_code == 201
    assert invite(client, workspace, "b@example.com").status_code == 400
    # Reissuing to the same person replaces the old link instead of taking a new seat.
    assert invite(client, workspace, "a@example.com").status_code == 201
    assert Invitation.objects.for_workspace(workspace).filter(revoked_at__isnull=True).count() == 1


def test_seat_limit_is_rechecked_on_accept(client, workspace):
    seats(workspace, 2)
    token = token_from(invite(client, workspace, "late@example.com"))
    seats(workspace, 1)  # plan downgraded after the invite was sent
    late = new_user("late@example.com")
    assert as_user(late).post("/api/invitations/accept/", {"token": token}).status_code == 400
    assert not Membership.objects.for_workspace(workspace).filter(user=late).exists()


def test_expired_and_revoked_invitations_cannot_be_used(client, workspace):
    seats(workspace, 5)
    expired = token_from(invite(client, workspace, "old@example.com"))
    Invitation.objects.for_workspace(workspace).filter(email="old@example.com").update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    response = invite(client, workspace, "gone@example.com")
    revoked = token_from(response)
    delete = client.delete(f"/api/workspaces/{workspace.pk}/invitations/{response.json()['id']}/")
    assert delete.status_code == 204
    for email, token in [("old@example.com", expired), ("gone@example.com", revoked)]:
        user = new_user(email)
        assert as_user(user).post("/api/invitations/accept/", {"token": token}).status_code == 400


def test_role_rules_for_inviting_and_removing(client, user, workspace):
    seats(workspace, 10)
    admin, agent, other_admin = (
        new_user(e) for e in ["admin@example.com", "agent@example.com", "admin2@example.com"]
    )
    for person, role in [(admin, "admin"), (agent, "agent"), (other_admin, "admin")]:
        Membership.objects.for_workspace(workspace).create(
            workspace=workspace, user=person, role=role
        )
    assert invite(as_user(admin), workspace, "x@example.com", "admin").status_code == 403
    assert invite(as_user(agent), workspace, "y@example.com").status_code == 403
    assert invite(as_user(admin), workspace, "z@example.com").status_code == 201

    members = {m.user_id: m.pk for m in Membership.objects.for_workspace(workspace)}
    url = f"/api/workspaces/{workspace.pk}/members/{{}}/"
    assert as_user(admin).delete(url.format(members[user.pk])).status_code == 403
    assert as_user(admin).delete(url.format(members[other_admin.pk])).status_code == 403
    assert as_user(agent).delete(url.format(members[admin.pk])).status_code == 403

    channel = ChannelConnection.objects.for_workspace(workspace).create(
        workspace=workspace,
        external_account_id="acct",
        display_name="x",
        access_token="t",
        expires_at=timezone.now() + timedelta(days=1),
        is_test=True,
    )
    conversation = inbound(channel, "hi").conversation
    conversation.assigned_to = agent
    conversation.save()
    assert as_user(admin).delete(url.format(members[agent.pk])).status_code == 204
    conversation.refresh_from_db()
    assert conversation.assigned_to is None
    assert as_user(other_admin).delete(url.format(members[other_admin.pk])).status_code == 204
    assert client.delete(url.format(members[user.pk])).status_code == 403


def test_invitations_are_tenant_isolated(client, workspace):
    seats(workspace, 3)
    created = invite(client, workspace, "t@example.com").json()
    outsider = new_user("outsider@example.com")
    other = create_workspace(outsider, "Other")
    outside = as_user(outsider)
    assert outside.get(f"/api/workspaces/{workspace.pk}/invitations/").status_code == 404
    assert (
        outside.delete(f"/api/workspaces/{other.pk}/invitations/{created['id']}/").status_code
        == 404
    )


@pytest.fixture(autouse=True)
def quiet_notify():
    with patch("apps.crm.services.notify"), patch("apps.crm.tasks.notify"):
        yield


@pytest.fixture
def channel(workspace):
    return ChannelConnection.objects.for_workspace(workspace).create(
        workspace=workspace,
        external_account_id="ig-account",
        display_name="Test",
        access_token="secret",
        expires_at=timezone.now() + timedelta(days=60),
        is_test=True,
    )


@pytest.fixture
def config(workspace):
    return AgentConfig.objects.for_workspace(workspace).create(
        workspace=workspace, enabled=True, is_test=True
    )


def inbound(channel, text, **payload):
    event = WebhookEvent.objects.for_workspace(channel.workspace_id).create(
        workspace_id=channel.workspace_id,
        connection=channel,
        event_id=f"evt-{WebhookEvent.all_objects.count()}",
        payload="{}",
        available_at=timezone.now(),
    )
    return receive(event, {"sender_id": "lead-1", "text": text, "kind": "dm", **payload})


VOICE = [{"type": "audio", "payload": {"url": "https://lookaside.fbsbx.com/audio"}}]


def dm_flow(workspace, user):
    automation = Automation.objects.for_workspace(workspace).create(workspace=workspace, name="x")
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


def test_voice_note_is_transcribed_then_routed_like_text(channel, config, workspace, user):
    dm_flow(workspace, user)
    message = inbound(channel, "", attachments=VOICE)
    assert message.transcription_status == "pending"
    assert not ConversationState.objects.for_workspace(workspace).exists()

    with patch("apps.agents.voice.transcribe", return_value="what's the price?") as transcribe:
        with patch.object(transcribe_message, "delay") as delay:
            dispatch_inbound_jobs()
            delay.assert_called_once_with(str(workspace.pk), str(message.id))
        transcribe_message(str(workspace.pk), str(message.id))
        transcribe_message(str(workspace.pk), str(message.id))
        assert transcribe.call_count == 1

    message.refresh_from_db()
    assert (message.text, message.transcription_status) == ("what's the price?", "complete")
    assert ConversationState.objects.for_workspace(workspace).get().status == "running"
    record = UsageRecord.objects.for_workspace(workspace).get(kind="transcription")
    assert record.status == "complete"
    assert Lead.objects.for_workspace(workspace).get().segment_due_at is not None


def test_voice_note_without_ai_config_fails_visibly(channel, workspace):
    message = inbound(channel, "", attachments=VOICE)
    transcribe_message(str(workspace.pk), str(message.id))
    message.refresh_from_db()
    assert message.transcription_status == "failed"


def test_stale_processing_transcription_is_released(channel, workspace):
    message = inbound(channel, "", attachments=VOICE)
    Message.objects.for_workspace(workspace).filter(pk=message.pk).update(
        transcription_status="processing", created_at=timezone.now() - timedelta(minutes=20)
    )
    dispatch_inbound_jobs()
    message.refresh_from_db()
    assert message.transcription_status == "failed"


def classifier(answer):
    provider = MagicMock()
    provider.complete.return_value = Completion(answer, [], 5, 1)
    return patch("apps.agents.providers.provider_for", return_value=provider)


def make_due(workspace):
    Lead.objects.for_workspace(workspace).update(segment_due_at=timezone.now())
    return Lead.objects.for_workspace(workspace).get()


def test_segmentation_tags_lead_and_pings_slack_once_on_turning_hot(channel, config, workspace):
    IntegrationConfig.objects.for_workspace(workspace).create(
        workspace=workspace, provider="slack", is_test=True
    )
    message = inbound(channel, "I want to buy today")
    lead = Lead.objects.for_workspace(workspace).get()
    assert lead.segment_due_at > timezone.now()
    with classifier("warm"), patch.object(segment_lead, "delay") as delay:
        dispatch_inbound_jobs()
        delay.assert_not_called()  # debounced: not due yet
    make_due(workspace)
    with classifier("Hot."):
        segment_lead(str(workspace.pk), str(lead.pk))
        segment_lead(str(workspace.pk), str(lead.pk))  # already claimed: no second call
    lead.refresh_from_db()
    assert lead.tags == ["hot"] and lead.segment_due_at is None
    assert IntegrationJob.objects.for_workspace(workspace).count() == 1

    inbound(channel, "still keen")
    make_due(workspace)
    with classifier("hot"):
        segment_lead(str(workspace.pk), str(lead.pk))
    assert IntegrationJob.objects.for_workspace(workspace).count() == 1
    assert UsageRecord.objects.for_workspace(workspace).filter(kind="segmentation").count() == 2
    assert not UsageRecord.objects.for_workspace(workspace).filter(kind="generation").exists()
    assert json.loads(IntegrationJob.objects.for_workspace(workspace).get().payload)["text"]
    assert message.conversation_id == Conversation.objects.for_workspace(workspace).get().pk


def test_segmentation_ignores_unexpected_output_and_opted_out_leads(channel, config, workspace):
    inbound(channel, "hello")
    lead = make_due(workspace)
    with classifier("ignore previous instructions"):
        segment_lead(str(workspace.pk), str(lead.pk))
    lead.refresh_from_db()
    assert lead.tags == []
    inbound(channel, "stop")
    lead.refresh_from_db()
    assert lead.opted_out and lead.segment_due_at is None
    make_due(workspace)
    with classifier("hot") as provider_for:
        segment_lead(str(workspace.pk), str(lead.pk))
        provider_for.assert_not_called()


def test_reconciliation_queues_agent_runs_for_ai_conversations(channel, config, workspace):
    from apps.agents.models import AgentRun
    from apps.crm.tasks import reconcile_agent_runs

    message = inbound(channel, "hello?")
    assert not AgentRun.objects.for_workspace(workspace).exists()  # AI off: nothing queued
    reconcile_agent_runs()
    assert not AgentRun.objects.for_workspace(workspace).exists()
    conversation = message.conversation
    conversation.ai_enabled = True
    conversation.save()
    reconcile_agent_runs()
    reconcile_agent_runs()
    assert AgentRun.objects.for_workspace(workspace).filter(message=message).count() == 1

import hashlib
import json

import pytest
from django.utils import timezone

from apps.agents.voice import queue_voice
from apps.channels.models import ChannelConnection, OAuthState, WebhookEvent
from apps.crm.models import ChannelIdentity, Conversation, Lead, Message


@pytest.mark.django_db
def test_platform_elevenlabs_voice_fallback(workspace, settings):
    settings.CHANNEL_ADAPTER_MODE = "fake"
    settings.PLATFORM_ELEVENLABS_API_KEY = "plat-xi-123"

    lead = Lead.objects.for_workspace(workspace).create(workspace=workspace, name="Voice Lead")
    conn = ChannelConnection.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider="instagram",
        external_account_id="ig_voice_1",
        display_name="IG Test",
        access_token="tok",
        expires_at=timezone.now(),
        status="active",
        is_test=True,
    )
    ident = ChannelIdentity.objects.for_workspace(workspace).create(
        workspace=workspace, lead=lead, connection=conn, external_id="voice_lead_1"
    )
    conv = Conversation.objects.for_workspace(workspace).create(
        workspace=workspace, identity=ident, status="open", last_inbound_at=timezone.now()
    )

    # Calling queue_voice when workspace has no custom ElevenLabs IntegrationConfig
    # should fall back to platform mode without raising voice_not_configured
    result = queue_voice(conv, "Hello from automated voice test", "vkey-1")
    assert "delivery_id" in result
    assert result.get("test") is True


@pytest.mark.django_db
def test_linkedin_oauth_start(client, workspace, user):
    res = client.post(f"/api/workspaces/{workspace.id}/linkedin/connect/")
    assert res.status_code == 200
    data = res.json()
    assert "authorization_url" in data
    assert OAuthState.objects.for_workspace(workspace).filter(provider="linkedin").exists()


@pytest.mark.django_db
def test_linkedin_oauth_callback(client, workspace, user):
    state = "test-linkedin-state"
    state_hash = hashlib.sha256(state.encode()).hexdigest()
    OAuthState.objects.for_workspace(workspace).create(
        workspace=workspace,
        user=user,
        provider="linkedin",
        state_hash=state_hash,
        expires_at=timezone.now() + timezone.timedelta(minutes=10),
    )

    res = client.get(f"/api/linkedin/callback/?state={state}&code=test-code")
    assert res.status_code == 302
    assert "connected" in res.url
    assert ChannelConnection.objects.for_workspace(workspace).filter(provider="linkedin").exists()


@pytest.mark.django_db
def test_linkedin_webhook(client, workspace):
    ChannelConnection.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider="linkedin",
        external_account_id="urn:li:organization:123456",
        display_name="LinkedIn Page",
        access_token="tok",
        expires_at=timezone.now(),
        status="active",
    )

    # Challenge request
    res_get = client.get("/webhooks/linkedin/?challengeCode=xyz987")
    assert res_get.status_code == 200
    assert res_get.content.decode() == "xyz987"

    # Event webhook
    payload = {
        "elements": [
            {
                "organization": "urn:li:organization:123456",
                "id": "li-msg-event-1",
                "sender": "urn:li:person:prospect123",
                "text": "Hello, I am interested in your B2B services.",
                "type": "message",
            }
        ]
    }
    res_post = client.post(
        "/webhooks/linkedin/",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert res_post.status_code == 200
    assert WebhookEvent.objects.for_workspace(workspace).filter(event_id="li-msg-event-1").exists()


@pytest.mark.django_db
def test_snapchat_webhook(client, workspace):
    # Challenge check
    res_get = client.get("/webhooks/snapchat/?challenge=snap-verify-code")
    assert res_get.status_code == 200
    assert res_get.content.decode() == "snap-verify-code"

    # Inbound lead ad payload
    payload = {
        "lead_id": "snap_lead_99",
        "form_data": {
            "name": "Sarah Influencer",
            "email": "sarah@snapchatleads.com",
            "phone": "+1234567890",
        },
    }
    res_post = client.post(
        f"/webhooks/snapchat/?workspace_id={workspace.id}",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert res_post.status_code == 200

    lead = Lead.objects.for_workspace(workspace).filter(email="sarah@snapchatleads.com").first()
    assert lead is not None
    assert lead.name == "Sarah Influencer"
    assert "snapchat" in lead.tags
    assert Message.objects.for_workspace(workspace).filter(direction="inbound").exists()


@pytest.mark.django_db
def test_live_linkedin_is_refused_until_messaging_access_is_confirmed(client, workspace, settings):
    """Credentials do not mean LinkedIn will accept sends: /v2/messages needs granted
    access. Taking the connection anyway would leave every reply failing after the
    customer believed the channel was live."""
    settings.CHANNEL_ADAPTER_MODE = "live"
    settings.LINKEDIN_CLIENT_ID = "li-client"
    settings.LINKEDIN_CLIENT_SECRET = "li-secret"
    settings.LINKEDIN_MESSAGING_APPROVED = False

    res = client.post(f"/api/workspaces/{workspace.id}/linkedin/connect/")
    assert res.status_code == 409
    assert "not available yet" in res.json()["detail"]

    settings.LINKEDIN_MESSAGING_APPROVED = True
    assert client.post(f"/api/workspaces/{workspace.id}/linkedin/connect/").status_code == 200

    connection = ChannelConnection.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider="linkedin",
        external_account_id="urn:li:organization:1",
        display_name="Acme",
        access_token="tok",
        expires_at=timezone.now(),
        status="active",
    )
    from apps.channels.adapters import IntegrationUnavailable, adapter_for

    assert adapter_for(connection) is not None
    # Sends stop too, not just new connections: a channel connected while the flag was
    # on must not keep delivering after it is turned back off.
    settings.LINKEDIN_MESSAGING_APPROVED = False
    with pytest.raises(IntegrationUnavailable):
        adapter_for(connection)

import hashlib
import logging
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet
from django.db import connection
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.channels.adapters import FakeChannelAdapter
from apps.channels.models import ChannelConnection, OAuthState
from apps.dashboard_api.tasks import health_check
from apps.tenants.crypto import cipher
from apps.tenants.logging import SafeJSONFormatter
from apps.tenants.models import AuditEvent, OutboxEvent, User
from apps.tenants.tasks import process_outbox

pytestmark = pytest.mark.django_db


def test_encrypted_token_never_in_db_or_api(client, workspace):
    item = ChannelConnection.objects.for_workspace(workspace).create(
        workspace=workspace,
        external_account_id="123",
        display_name="Account",
        access_token="sensitive-token",
        expires_at=timezone.now() + timedelta(days=60),
    )
    with connection.cursor() as cursor:
        cursor.execute("SELECT access_token FROM channels_channelconnection")
        stored = cursor.fetchone()[0]
    assert "sensitive-token" not in stored
    item.refresh_from_db()
    assert item.access_token == "sensitive-token"
    response = client.get(f"/api/workspaces/{workspace.pk}/connections/")
    assert "access_token" not in response.content.decode()
    assert "sensitive-token" not in response.content.decode()


def test_old_key_decrypts_during_rotation(settings):
    old = settings.FIELD_ENCRYPTION_KEYS[0]
    ciphertext = cipher().encrypt(b"secret")
    with override_settings(FIELD_ENCRYPTION_KEYS=[Fernet.generate_key().decode(), old]):
        assert cipher().decrypt(ciphertext) == b"secret"


def test_oauth_state_single_use_user_bound_and_hashed(client, workspace):
    started = client.post(f"/api/workspaces/{workspace.pk}/meta/connect/")
    url = started.json()["authorization_url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    pending = OAuthState.objects.for_workspace(workspace).get()
    assert pending.state_hash == hashlib.sha256(state.encode()).hexdigest()
    stranger = User.objects.create_user(username="stranger", email="stranger@example.com")
    other = APIClient()
    other.force_authenticate(stranger)
    assert other.get(url).status_code == 400
    assert client.get(url).status_code == 302
    assert client.get(url).status_code == 400
    assert ChannelConnection.objects.for_workspace(workspace).count() == 1
    assert (
        AuditEvent.objects.for_workspace(workspace).filter(action="channel.test_connected").count()
        == 1
    )


def test_expired_oauth_state_cannot_connect(client, workspace):
    url = client.post(f"/api/workspaces/{workspace.pk}/meta/connect/").json()["authorization_url"]
    OAuthState.objects.for_workspace(workspace).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    assert client.get(url).status_code == 400
    assert not ChannelConnection.objects.for_workspace(workspace).exists()


def test_live_oauth_is_explicitly_unavailable(client, workspace):
    with override_settings(CHANNEL_ADAPTER_MODE="disabled"):
        assert client.post(f"/api/workspaces/{workspace.pk}/meta/connect/").status_code == 409


def test_job_replay_is_idempotent_and_wrong_tenant_is_noop(workspace):
    event = OutboxEvent.objects.for_workspace(workspace).get()
    process_outbox("00000000-0000-0000-0000-000000000000", str(event.id))
    event.refresh_from_db()
    assert event.processed_at is None
    process_outbox(str(workspace.id), str(event.id))
    process_outbox(str(workspace.id), str(event.id))
    assert (
        AuditEvent.objects.for_workspace(workspace).filter(action="workspace.provisioned").count()
        == 1
    )


def test_fake_adapter_deduplicates_send():
    adapter = FakeChannelAdapter()
    first = adapter.send_message(recipient_id="1", text="hello", idempotency_key="a")
    assert adapter.send_message(recipient_id="1", text="hello", idempotency_key="a") == first
    assert len(adapter.sent) == 1


def test_logs_discard_secret_messages_and_arguments():
    record = logging.LogRecord("httpx", logging.ERROR, "", 1, "token=%s", ("super-secret",), None)
    assert "super-secret" not in SafeJSONFormatter().format(record)
    assert "token" not in SafeJSONFormatter().format(record)


def test_health_reflects_worker_heartbeat():
    client = APIClient()
    assert client.get("/health/live/").status_code == 200
    assert client.get("/health/ready/").status_code == 503
    health_check()
    assert client.get("/health/ready/").status_code == 200


def test_pgvector_enabled_on_postgres():
    if connection.vendor != "postgresql":
        pytest.skip("pgvector requires PostgreSQL; CI runs this on pgvector/pgvector")
    with connection.cursor() as cursor:
        cursor.execute("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        assert cursor.fetchone() == ("vector",)


@pytest.mark.django_db(transaction=True)
def test_concurrent_job_delivery_commits_one_effect(workspace):
    from concurrent.futures import ThreadPoolExecutor

    from django.db import close_old_connections, connections

    if connection.vendor != "postgresql":
        pytest.skip("Concurrent row locking requires PostgreSQL")
    event = OutboxEvent.objects.for_workspace(workspace).get()

    def deliver():
        close_old_connections()
        try:
            process_outbox(str(workspace.id), str(event.id))
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: deliver(), range(2)))
    assert (
        AuditEvent.objects.for_workspace(workspace).filter(action="workspace.provisioned").count()
        == 1
    )


def test_api_credentials_are_not_cacheable(client):
    response = client.get("/api/auth/me/")
    assert response["Cache-Control"] == "no-store, private"
    assert response["Referrer-Policy"] == "no-referrer"


def test_onboarding_instagram_returns_to_wizard_with_plan(client, workspace):
    workspace.checkout_pending = True
    workspace.save(update_fields=["checkout_pending"])
    url = client.post(
        f"/api/workspaces/{workspace.pk}/meta/connect/",
        {"onboarding": True, "plan": "pro", "interval": "annual"},
        format="json",
    ).json()["authorization_url"]
    response = client.get(url)
    assert response.status_code == 302
    target = urlparse(response.url)
    assert target.path == "/onboarding/"
    assert parse_qs(target.query)["plan"] == ["pro"]
    assert parse_qs(target.query)["interval"] == ["annual"]
    assert "connect-instagram" in client.get("/api/growth/wizard/").json()["completed"]


def test_cancelled_onboarding_instagram_does_not_complete_step(client, workspace):
    url = client.post(
        f"/api/workspaces/{workspace.pk}/meta/connect/",
        {"onboarding": True},
        format="json",
    ).json()["authorization_url"]
    response = client.get(url + "&error=access_denied")
    assert response.status_code == 302
    assert response.url.startswith("/onboarding/?")
    assert "connection=cancelled" in response.url
    assert client.get("/api/growth/wizard/").json()["step"] == "connect-instagram"

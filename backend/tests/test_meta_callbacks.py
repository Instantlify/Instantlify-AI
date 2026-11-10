import base64
import hashlib
import hmac
import json
from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.channels.models import ChannelConnection, MetaDataDeletion

pytestmark = pytest.mark.django_db


def signed(payload, secret="app-secret"):
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode().rstrip("=") + "." + body


@pytest.fixture
def connection(workspace, settings):
    settings.META_APP_SECRET = "app-secret"
    settings.PUBLIC_APP_URL = "https://app.example.com"
    return ChannelConnection.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider="instagram",
        external_account_id="17841400000",
        display_name="IG",
        access_token="tok",
        profile={"username": "acme"},
        expires_at=timezone.now() + timedelta(days=30),
        status="active",
    )


def test_deauthorize_disconnects_and_wipes_tokens(connection):
    res = Client().post(
        "/webhooks/meta/deauthorize/",
        {"signed_request": signed({"algorithm": "HMAC-SHA256", "user_id": "17841400000"})},
    )
    assert res.status_code == 200
    connection.refresh_from_db()
    assert (connection.status, connection.access_token, connection.profile) == (
        "disconnected",
        "",
        {},
    )


def test_data_deletion_returns_code_and_status_page(connection):
    res = Client().post(
        "/webhooks/meta/data-deletion/",
        {"signed_request": signed({"algorithm": "HMAC-SHA256", "user_id": "17841400000"})},
    )
    body = res.json()
    assert body["url"] == f"https://app.example.com/data-deletion/?code={body['confirmation_code']}"
    record = MetaDataDeletion.objects.get(code=body["confirmation_code"])
    assert record.connections_cleared == 1 and "17841400000" not in record.user_hash
    status = Client().get(f"/api/public/data-deletion/{record.code}/").json()
    assert status["status"] == "completed" and status["connections_disconnected"] == 1
    assert Client().get("/api/public/data-deletion/unknown/").status_code == 404


@pytest.mark.parametrize(
    "value",
    [
        "garbage",
        signed({"algorithm": "HMAC-SHA256", "user_id": "1"}, secret="wrong"),
        signed({"algorithm": "none", "user_id": "1"}),
        signed({"algorithm": "HMAC-SHA256"}),
    ],
)
def test_bad_signed_requests_are_rejected(connection, value):
    for path in ("/webhooks/meta/deauthorize/", "/webhooks/meta/data-deletion/"):
        assert Client().post(path, {"signed_request": value}).status_code == 400
    connection.refresh_from_db()
    assert connection.status == "active"

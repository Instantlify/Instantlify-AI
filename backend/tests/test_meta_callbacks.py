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
    assert Client().get(f"/api/public/data-deletion/{record.code}/").json()["status"] == "pending"
    from apps.channels.meta_deletion import process_meta_deletion

    process_meta_deletion("meta", record.pk)
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


def request_deletion(subject="17841400000", secret="app-secret"):
    return (
        Client()
        .post(
            "/webhooks/meta/data-deletion/",
            {"signed_request": signed({"algorithm": "HMAC-SHA256", "user_id": subject}, secret)},
        )
        .json()
    )


def test_erasure_removes_messages_and_unshared_contact(connection, workspace):
    from apps.channels.meta_deletion import process_meta_deletion
    from apps.crm.models import ChannelIdentity, Conversation, Lead, Message

    lead = Lead.objects.for_workspace(workspace).create(workspace=workspace, name="Private")
    identity = ChannelIdentity.objects.for_workspace(workspace).create(
        workspace=workspace, lead=lead, connection=connection, external_id="customer"
    )
    conversation = Conversation.objects.for_workspace(workspace).create(
        workspace=workspace, identity=identity
    )
    message = Message.objects.for_workspace(workspace).create(
        workspace=workspace, conversation=conversation, direction="in", text="Private message"
    )
    record = MetaDataDeletion.objects.get(code=request_deletion()["confirmation_code"])
    process_meta_deletion("meta", record.pk)
    record.refresh_from_db()
    assert record.status == "completed" and record.subject_id == ""
    assert record.connections_deleted == 1
    assert not ChannelConnection.all_objects.filter(pk=connection.pk).exists()
    assert not Message.all_objects.filter(pk=message.pk).exists()
    assert not Lead.all_objects.filter(pk=lead.pk).exists()


def test_unknown_identity_requires_review_and_status_is_private(connection):
    from apps.channels.meta_deletion import process_meta_deletion

    record = MetaDataDeletion.objects.get(code=request_deletion("999")["confirmation_code"])
    process_meta_deletion("meta", record.pk)
    record.refresh_from_db()
    assert record.status == "needs_review" and record.completed_at is None
    response = Client().get(f"/api/public/data-deletion/{record.code}/")
    assert set(response.json()) == {
        "confirmation_code",
        "status",
        "requested_at",
        "completed_at",
        "connections_disconnected",
        "connections_deleted",
    }
    assert "no-store" in response["Cache-Control"]
    connection.refresh_from_db()
    assert connection.status == "active"


def test_replayed_callback_does_not_disconnect_reconnected_account(connection):
    from apps.channels.meta_deletion import process_meta_deletion

    first = request_deletion()
    record = MetaDataDeletion.objects.get(code=first["confirmation_code"])
    process_meta_deletion("meta", record.pk)
    replacement = ChannelConnection.all_objects.create(
        workspace=connection.workspace,
        provider="instagram",
        external_account_id="17841400000",
        display_name="Reconnected",
        access_token="new-token",
        expires_at=timezone.now(),
    )
    assert request_deletion() == first
    replacement.refresh_from_db()
    assert replacement.access_token == "new-token" and replacement.status == "active"
    assert MetaDataDeletion.objects.count() == 1


def test_app_secret_and_authorizer_scope(connection, settings):
    from apps.channels.meta_deletion import process_meta_deletion

    settings.MESSENGER_APP_SECRET = "messenger-secret"
    page = ChannelConnection.all_objects.create(
        workspace=connection.workspace,
        provider="messenger",
        external_account_id="page-id",
        meta_authorizer_id="17841400000",
        display_name="Page",
        access_token="page-token",
        expires_at=timezone.now(),
    )
    record = MetaDataDeletion.objects.get(
        code=request_deletion(secret="messenger-secret")["confirmation_code"]
    )
    process_meta_deletion("meta", record.pk)
    record.refresh_from_db()
    assert record.status == "completed"
    assert not ChannelConnection.all_objects.filter(pk=page.pk).exists()
    connection.refresh_from_db()
    assert connection.status == "active" and connection.access_token == "tok"


def test_manual_completion_requires_verified_operator_attestation(connection):
    from django.core.management import call_command
    from django.core.management.base import CommandError

    record = MetaDataDeletion.objects.get(code=request_deletion("999")["confirmation_code"])
    with pytest.raises(CommandError):
        call_command("review_meta_deletion", record.code)
    record.refresh_from_db()
    assert record.status == "pending"
    call_command(
        "review_meta_deletion",
        record.code,
        confirm_erasure=True,
        reason="Privacy case 123: independently verified erasure scope.",
    )
    record.refresh_from_db()
    assert record.status == "completed" and record.completed_at and record.subject_id == ""


def test_financial_records_are_not_cascaded_away(connection):
    from apps.billing.models import Offer, Payment
    from apps.channels.meta_deletion import process_meta_deletion
    from tests.test_meta_client import inbound

    message = inbound(connection, "Order")
    workspace = connection.workspace
    offer = Offer.objects.for_workspace(workspace).create(
        workspace=workspace, name="Order", amount_cents=100
    )
    payment = Payment.objects.for_workspace(workspace).create(
        workspace=workspace,
        offer=offer,
        conversation=message.conversation,
        lead=message.conversation.identity.lead,
        amount_cents=100,
        idempotency_key="payment",
    )
    record = MetaDataDeletion.objects.get(code=request_deletion()["confirmation_code"])
    process_meta_deletion("meta", record.pk)
    record.refresh_from_db()
    assert record.status == "needs_review" and record.completed_at is None
    assert Payment.all_objects.filter(pk=payment.pk).exists()
    assert ChannelConnection.all_objects.filter(pk=connection.pk).exists()


def test_shared_contact_requires_review_and_export_snapshot_expires(connection):
    from apps.channels.meta_deletion import process_meta_deletion
    from apps.crm.models import ChannelIdentity, Lead
    from apps.tenants.models import DataOperation
    from tests.test_meta_client import inbound

    message = inbound(connection, "Private")
    lead = message.conversation.identity.lead
    other = ChannelConnection.all_objects.create(
        workspace=connection.workspace,
        provider="telegram",
        external_account_id="bot",
        display_name="Other channel",
        access_token="other-token",
        expires_at=timezone.now(),
    )
    ChannelIdentity.all_objects.create(
        workspace=connection.workspace, lead=lead, connection=other, external_id="other-user"
    )
    export = DataOperation.all_objects.create(
        workspace=connection.workspace, kind="export", status="complete", result="private snapshot"
    )
    record = MetaDataDeletion.objects.get(code=request_deletion()["confirmation_code"])
    process_meta_deletion("meta", record.pk)
    record.refresh_from_db()
    export.refresh_from_db()
    assert record.status == "needs_review" and record.connections_deleted == 1
    assert export.result == "" and export.status == "expired"
    assert Lead.all_objects.filter(pk=lead.pk).exists()
    other.refresh_from_db()
    assert other.access_token == "other-token"


@pytest.mark.parametrize("subject", [True, {}, [], "x", "1" * 201])
def test_invalid_subjects_are_rejected(connection, subject):
    assert (
        Client()
        .post(
            "/webhooks/meta/data-deletion/",
            {"signed_request": signed({"algorithm": "HMAC-SHA256", "user_id": subject})},
        )
        .status_code
        == 400
    )

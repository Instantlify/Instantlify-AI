import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.channels.models import ChannelConnection, Delivery
from apps.crm.models import ChannelIdentity, Conversation, Lead, Message, MessageAttachment

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _conversation(workspace, provider="instagram", is_test=False):
    connection = ChannelConnection.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider=provider,
        external_account_id=f"{provider}-acct",
        display_name="Account",
        access_token="tok",
        expires_at=timezone.now() + timezone.timedelta(days=30),
        status="active",
        is_test=is_test,
    )
    lead = Lead.objects.for_workspace(workspace).create(workspace=workspace, name="Lead")
    identity = ChannelIdentity.objects.for_workspace(workspace).create(
        workspace=workspace, lead=lead, connection=connection, external_id="cust-1"
    )
    return Conversation.objects.for_workspace(workspace).create(
        workspace=workspace, identity=identity, status="open", last_inbound_at=timezone.now()
    )


def _url(workspace, conversation):
    return f"/api/workspaces/{workspace.pk}/conversations/{conversation.pk}/messages/"


@pytest.mark.django_db
def test_photo_is_stored_and_sent_as_real_media_with_caption_after(client, workspace, settings):
    settings.PUBLIC_APP_URL = "https://app.example.com"
    conversation = _conversation(workspace)
    res = client.post(
        _url(workspace, conversation),
        {"file": SimpleUploadedFile("menu.png", PNG, content_type="image/png"), "text": "Our menu"},
        format="multipart",
        HTTP_IDEMPOTENCY_KEY="k1",
    )
    assert res.status_code == 202
    attachment = MessageAttachment.objects.for_workspace(workspace).get()
    assert attachment.filename == "menu.png" and attachment.size == len(PNG)

    deliveries = list(Delivery.objects.for_workspace(workspace).order_by("available_at"))
    media = json.loads(deliveries[0].payload)
    assert media["kind"] == "media" and media["media_type"] == "image"
    assert media["media_url"].startswith("https://app.example.com/media/attachment/")
    assert json.loads(deliveries[1].payload)["text"] == "Our menu"
    assert not Message.objects.for_workspace(workspace).filter(text__startswith="[Image").exists()

    # The signed link serves the exact bytes the provider will fetch.
    path = media["media_url"].removeprefix("https://app.example.com")
    served = client.get(path)
    assert served.status_code == 200 and served.content == PNG
    assert served["Content-Type"] == "image/png"
    assert client.get("/media/attachment/forged-token/").status_code == 403

    # Retrying the same request does not store or send the file twice.
    client.post(
        _url(workspace, conversation),
        {"file": SimpleUploadedFile("menu.png", PNG, content_type="image/png"), "text": "Our menu"},
        format="multipart",
        HTTP_IDEMPOTENCY_KEY="k1",
    )
    assert MessageAttachment.objects.for_workspace(workspace).count() == 1
    assert Delivery.objects.for_workspace(workspace).count() == 2


@pytest.mark.django_db
def test_attachment_rejects_wrong_type_spoofed_content_and_oversize(client, workspace, settings):
    settings.PUBLIC_APP_URL = "https://app.example.com"
    conversation = _conversation(workspace)
    url = _url(workspace, conversation)
    cases = [
        SimpleUploadedFile("doc.pdf", b"%PDF-1.4", content_type="application/pdf"),
        SimpleUploadedFile("fake.png", b"<html>not an image</html>", content_type="image/png"),
        SimpleUploadedFile("big.png", PNG + b"\x00" * (5 * 1024 * 1024), content_type="image/png"),
    ]
    for index, upload in enumerate(cases):
        res = client.post(
            url, {"file": upload}, format="multipart", HTTP_IDEMPOTENCY_KEY=f"bad{index}"
        )
        assert res.status_code == 400
    assert not MessageAttachment.objects.for_workspace(workspace).exists()
    assert not Delivery.objects.for_workspace(workspace).exists()


@pytest.mark.django_db
def test_attachment_needs_https_origin_for_live_channels(client, workspace, settings):
    settings.PUBLIC_APP_URL = "http://localhost:3000"
    live = _conversation(workspace)
    res = client.post(
        _url(workspace, live),
        {"file": SimpleUploadedFile("a.png", PNG, content_type="image/png")},
        format="multipart",
        HTTP_IDEMPOTENCY_KEY="k",
    )
    assert res.status_code == 400
    assert not MessageAttachment.objects.for_workspace(workspace).exists()


@pytest.mark.django_db
def test_saved_replies_are_shared_and_replaced_as_a_list(client, workspace):
    url = f"/api/workspaces/{workspace.pk}/saved-replies/"
    assert client.get(url).json() == {"replies": []}
    res = client.put(url, {"replies": ["Hi there", " Hi there ", "Price is $20"]}, format="json")
    assert res.status_code == 200
    assert res.json() == {"replies": ["Hi there", "Price is $20"]}
    assert client.get(url).json() == {"replies": ["Hi there", "Price is $20"]}
    assert client.put(url, {"replies": ["Price is $20"]}, format="json").status_code == 200
    assert client.get(url).json() == {"replies": ["Price is $20"]}
    assert client.put(url, {"replies": [""]}, format="json").status_code == 400
    assert client.put(url, {"replies": ["x"] * 51}, format="json").status_code == 400

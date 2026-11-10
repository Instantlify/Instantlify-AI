from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from django.db import close_old_connections, connection
from django.utils import timezone
from rest_framework.test import APIClient

from apps.crm.models import Conversation, Message
from apps.crm.services import queue_reply


@pytest.mark.django_db
def test_messages_with_identical_timestamps_keep_creation_order(workspace, client):
    anonymous = APIClient()
    url = f"/api/public/webchat/{workspace.pk}/"
    fixed = timezone.now()
    with patch("django.utils.timezone.now", return_value=fixed):
        for text in ("First", "Second"):
            assert (
                anonymous.post(
                    url, {"visitor": "visitor-one", "text": text}, format="json"
                ).status_code
                == 201
            )
        conversation = Conversation.objects.for_workspace(workspace).get()
        queue_reply(conversation, "Third", "ordered-reply")
    assert list(Message.objects.for_workspace(workspace).values_list("sequence", flat=True)) == [
        1,
        2,
        3,
    ]
    thread = anonymous.get(url, {"visitor": "visitor-one"}).json()["messages"]
    assert [message["text"] for message in thread] == ["First", "Second", "Third"]
    inbox = client.get(
        f"/api/workspaces/{workspace.pk}/conversations/{conversation.pk}/messages/"
    ).json()
    assert [message["text"] for message in inbox["results"]] == ["Third", "Second", "First"]


@pytest.mark.django_db
def test_long_webchat_threads_return_the_latest_two_hundred_messages(workspace):
    anonymous = APIClient()
    url = f"/api/public/webchat/{workspace.pk}/"
    assert (
        anonymous.post(url, {"visitor": "visitor-one", "text": "First"}, format="json").status_code
        == 201
    )
    conversation = Conversation.objects.for_workspace(workspace).get()
    Message.objects.for_workspace(workspace).bulk_create(
        [
            Message(
                workspace=workspace,
                conversation=conversation,
                sequence=i,
                direction="inbound",
                text=f"Message {i}",
            )
            for i in range(2, 206)
        ]
    )
    thread = anonymous.get(url, {"visitor": "visitor-one"}).json()["messages"]
    assert (
        len(thread) == 200
        and thread[0]["text"] == "Message 6"
        and thread[-1]["text"] == "Message 205"
    )


@pytest.mark.django_db(transaction=True)
def test_concurrent_message_numbers_are_unique_on_postgresql(workspace):
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL conversation row locks")
    anonymous = APIClient()
    assert (
        anonymous.post(
            f"/api/public/webchat/{workspace.pk}/",
            {"visitor": "visitor-one", "text": "Start"},
            format="json",
        ).status_code
        == 201
    )
    conversation = Conversation.objects.for_workspace(workspace).get()

    def create(index):
        close_old_connections()
        try:
            return (
                Message.objects.for_workspace(workspace.pk)
                .create(
                    workspace_id=workspace.pk,
                    conversation_id=conversation.pk,
                    direction="inbound",
                    text=f"Concurrent {index}",
                )
                .sequence
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=4) as executor:
        numbers = list(executor.map(create, range(8)))
    assert sorted(numbers) == list(range(2, 10))

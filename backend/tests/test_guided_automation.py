"""Observable guided-builder behavior: consent, email capture, CRM actions and isolation."""

import json
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.automations.models import Automation, ConversationState
from apps.automations.tasks import step
from apps.channels.models import ChannelConnection, Delivery, WebhookEvent
from apps.crm.models import Lead
from apps.crm.services import receive
from apps.tenants.models import Membership, User
from apps.tenants.services import create_workspace

pytestmark = pytest.mark.django_db
TOKEN = "instantlify:continue:test-button"


@pytest.fixture(autouse=True)
def quiet_notify():
    with patch("apps.crm.services.notify"):
        yield


@pytest.fixture
def channel(workspace):
    return ChannelConnection.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider="instagram",
        external_account_id="guided-account",
        display_name="Guided",
        access_token="test",
        is_test=True,
        expires_at=timezone.now() + timedelta(days=30),
    )


def flow(*actions, connection=None, opening=False, email=False):
    nodes = []
    if opening:
        nodes += [
            {
                "id": "opening",
                "data": {
                    "kind": "send_buttons",
                    "text": "Want the guide?",
                    "buttons": [{"type": "postback", "title": "Send the guide", "payload": TOKEN}],
                },
            },
            {"id": "accept", "data": {"kind": "wait", "expected_reply": TOKEN}},
        ]
    if email:
        nodes += [
            {"id": "ask", "data": {"kind": "send_message", "text": "Your email?"}},
            {
                "id": "email",
                "data": {"kind": "capture_email", "retry_text": "Please try a valid email."},
            },
        ]
    nodes += [
        {
            "id": "resources",
            "data": {
                "kind": "send_buttons",
                "text": "Your guide",
                "buttons": [
                    {"type": "web_url", "title": "Read", "url": "https://example.com/guide"}
                ],
            },
        }
    ]
    nodes += [{"id": f"action-{i}", "data": data} for i, data in enumerate(actions)]
    if not actions or actions[-1]["kind"] != "transfer":
        nodes.append({"id": "done", "data": {"kind": "end"}})
    return {
        **({"connection_id": str(connection.pk)} if connection else {}),
        "start": nodes[0]["id"],
        "triggers": [{"kind": "comment", "keyword": "guide", "channel": "instagram"}],
        "nodes": nodes,
        "edges": [
            {"source": first["id"], "target": second["id"]}
            for first, second in zip(nodes, nodes[1:], strict=False)
        ],
    }


def publish(client, workspace, graph):
    url = f"/api/workspaces/{workspace.pk}/automations/"
    created = client.post(url, {"name": "Guided test", "draft": graph}, format="json")
    assert created.status_code == 201, created.content
    response = client.post(f"{url}{created.json()['id']}/publish/", {"graph": graph}, format="json")
    return response


def inbound(channel, text, kind="dm", **extra):
    event = WebhookEvent.objects.for_workspace(channel.workspace_id).create(
        workspace_id=channel.workspace_id,
        connection=channel,
        event_id=f"evt-{WebhookEvent.all_objects.count()}",
        payload="{}",
        available_at=timezone.now(),
    )
    return receive(
        event,
        {
            "sender_id": "person",
            "text": text,
            "kind": kind,
            **({"comment_id": event.event_id} if kind == "comment" else {}),
            **extra,
        },
    )


def run(state, limit=120):
    for _ in range(limit):
        state.refresh_from_db()
        if state.status != "running":
            return state
        step(str(state.workspace_id), str(state.pk))
    raise AssertionError("Execution did not stop within its step budget")


def sent(workspace):
    return [
        json.loads(item.payload)
        for item in Delivery.objects.for_workspace(workspace).order_by("created_at", "id")
    ]


def test_resources_wait_for_matching_private_opt_in_then_apply_real_crm_actions(
    client, workspace, channel, user
):
    response = publish(
        client,
        workspace,
        flow(
            {"kind": "add_tag", "tag": "guide-requested"},
            {"kind": "assign_member", "user_id": user.pk},
            connection=channel,
            opening=True,
        ),
    )
    assert response.status_code == 200, response.content
    inbound(channel, "guide", "comment")
    state = run(ConversationState.objects.for_workspace(workspace).get())
    assert state.status == "waiting"
    assert [p["text"] for p in sent(workspace)] == ["Want the guide?"]
    assert sent(workspace)[0]["buttons"][0]["type"] == "postback"
    inbound(channel, TOKEN, "comment")
    inbound(channel, "an unrelated DM")
    assert run(state).status == "waiting"
    inbound(channel, TOKEN)
    assert run(state).status == "completed"
    assert [p["text"] for p in sent(workspace)] == ["Want the guide?", "Your guide"]
    assert Lead.objects.for_workspace(workspace).get().tags == ["guide-requested"]
    state.conversation.refresh_from_db()
    assert state.conversation.assigned_to_id == user.pk


def test_email_is_validated_before_saving_or_releasing_resources(client, workspace, channel):
    assert publish(client, workspace, flow(email=True)).status_code == 200
    inbound(channel, "guide", "comment")
    state = run(ConversationState.objects.for_workspace(workspace).get())
    inbound(channel, "not an email")
    assert run(state).status == "waiting"
    assert Lead.objects.for_workspace(workspace).get().email == ""
    assert [p["text"] for p in sent(workspace)] == ["Your email?", "Please try a valid email."]
    inbound(channel, " person@example.com ")
    assert run(state).status == "completed"
    assert Lead.objects.for_workspace(workspace).get().email == "person@example.com"
    assert sent(workspace)[-1]["text"] == "Your guide"


def test_selected_account_does_not_run_on_a_different_account(client, workspace, channel):
    from tests.conftest import set_limits

    set_limits(workspace, max_instagram_accounts=2)
    second = ChannelConnection.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider="instagram",
        external_account_id="second",
        access_token="test",
        is_test=True,
        expires_at=timezone.now() + timedelta(days=30),
    )
    assert publish(client, workspace, flow(connection=channel)).status_code == 200
    inbound(second, "guide", "comment")
    assert not ConversationState.objects.for_workspace(workspace).exists()
    inbound(channel, "guide", "comment")
    assert ConversationState.objects.for_workspace(workspace).count() == 1


@pytest.mark.parametrize("reference", ["account", "member", "automation"])
def test_foreign_tenant_references_cannot_be_published(client, workspace, channel, reference):
    other_user = User.objects.create_user(
        username="other", email="other@example.com", password="test"
    )
    other = create_workspace(other_user, "Other")
    if reference == "account":
        foreign = ChannelConnection.objects.for_workspace(other).create(
            workspace=other,
            external_account_id="foreign",
            access_token="test",
            is_test=True,
            expires_at=timezone.now() + timedelta(days=30),
        )
        graph = flow(connection=foreign)
    elif reference == "member":
        graph = flow({"kind": "assign_member", "user_id": other_user.pk})
    else:
        target = Automation.objects.for_workspace(other).create(
            workspace=other, name="Foreign", enabled=True, published=flow()
        )
        graph = flow({"kind": "transfer", "automation_id": str(target.pk)})
    assert publish(client, workspace, graph).status_code == 400


def test_removed_teammate_fails_closed_at_execution(client, workspace, channel):
    teammate = User.objects.create_user(
        username="agent", email="agent@example.com", password="test"
    )
    Membership.objects.for_workspace(workspace).create(
        workspace=workspace, user=teammate, role="agent"
    )
    assert (
        publish(
            client, workspace, flow({"kind": "assign_member", "user_id": teammate.pk})
        ).status_code
        == 200
    )
    Membership.objects.for_workspace(workspace).filter(user=teammate).delete()
    inbound(channel, "guide", "comment")
    assert run(ConversationState.objects.for_workspace(workspace).get()).status == "failed"


def test_continuation_checks_target_availability_and_preserves_budget(client, workspace, channel):
    target = publish(client, workspace, flow())
    assert target.status_code == 200
    assert (
        publish(
            client, workspace, flow({"kind": "transfer", "automation_id": target.json()["id"]})
        ).status_code
        == 200
    )
    source = Automation.objects.for_workspace(workspace).exclude(pk=target.json()["id"]).get()
    # Run the source deterministically; its keyword precedes the older destination's trigger.
    from apps.automations.services import start_flow

    message = inbound(channel, "unmatched")
    state = start_flow(message.conversation, source, message=message)
    target_graph = flow({"kind": "transfer", "automation_id": str(source.pk)})
    Automation.objects.for_workspace(workspace).filter(pk=target.json()["id"]).update(
        published=target_graph
    )
    assert run(state).status == "stopped"
    assert state.steps == 100
    assert state.error_code == "execution_guard"


def test_import_keeps_account_scope_for_review_before_republishing(client, workspace, channel):
    response = publish(client, workspace, flow(connection=channel))
    url = f"/api/workspaces/{workspace.pk}/automations/"
    exported = client.get(f"{url}{response.json()['id']}/export/").json()
    imported = client.post(f"{url}import/", {"template": exported}, format="json")
    assert imported.status_code == 201, imported.content
    assert imported.json()["draft"]["connection_id"] == str(channel.pk)
    assert imported.json()["enabled"] is False


def test_duplicate_tag_steps_do_not_duplicate_a_contact_tag(client, workspace, channel):
    action = {"kind": "add_tag", "tag": "guide"}
    assert publish(client, workspace, flow(action, action)).status_code == 200
    inbound(channel, "guide", "comment")
    assert run(ConversationState.objects.for_workspace(workspace).get()).status == "completed"
    assert Lead.objects.for_workspace(workspace).get().tags == ["guide"]


def test_paused_destination_fails_closed_after_source_was_published(client, workspace, channel):
    from apps.automations.services import start_flow

    target = publish(client, workspace, flow())
    source = publish(
        client, workspace, flow({"kind": "transfer", "automation_id": target.json()["id"]})
    )
    message = inbound(channel, "unmatched")
    source_item = Automation.objects.for_workspace(workspace).get(pk=source.json()["id"])
    state = start_flow(message.conversation, source_item, message=message)
    Automation.objects.for_workspace(workspace).filter(pk=target.json()["id"]).update(enabled=False)
    assert run(state).status == "failed"
    assert len(sent(workspace)) == 1


@pytest.mark.parametrize("payload", [None, "", "x" * 65, 123])
def test_invalid_reply_button_payloads_are_rejected(client, workspace, payload):
    graph = flow(opening=True)
    graph["nodes"][0]["data"]["buttons"][0]["payload"] = payload
    assert publish(client, workspace, graph).status_code == 400


def test_telegram_reply_buttons_and_resource_links_reach_the_transport(channel):
    from apps.channels.providers import TelegramAdapter

    adapter = TelegramAdapter(channel)
    with patch.object(adapter, "call", return_value={"message_id": 5}) as send:
        adapter.send_message(
            recipient_id="person",
            text="Continue?",
            idempotency_key="test",
            buttons=[
                {"type": "postback", "title": "Continue", "payload": TOKEN},
                {"type": "web_url", "title": "Guide", "url": "https://example.com"},
            ],
        )
    assert send.call_args.args == (
        "sendMessage",
        {
            "chat_id": "person",
            "text": "Continue?",
            "reply_markup": {
                "inline_keyboard": [
                    [{"text": "Continue", "callback_data": TOKEN}],
                    [{"text": "Guide", "url": "https://example.com"}],
                ]
            },
        },
    )


def test_whatsapp_uses_real_reply_buttons_and_preserves_resource_urls(channel):
    from apps.channels.providers import WhatsAppAdapter

    adapter = WhatsAppAdapter(channel)
    with patch.object(adapter, "_send", return_value="sent") as send:
        adapter.send_message(
            recipient_id="person",
            text="Continue?",
            idempotency_key="test",
            buttons=[
                {"type": "postback", "title": "Continue", "payload": TOKEN},
            ],
        )
        body = send.call_args.args[1]
        assert body["type"] == "interactive"
        assert body["interactive"]["action"]["buttons"][0]["reply"]["id"] == TOKEN
        adapter.send_message(
            recipient_id="person",
            text="Your guide",
            idempotency_key="other",
            buttons=[
                {"type": "web_url", "title": "Read", "url": "https://example.com/guide"},
            ],
        )
        assert (
            send.call_args.args[1]["text"]["body"]
            == "Your guide\n\nRead: https://example.com/guide"
        )


def test_meta_postbacks_without_mid_have_stable_retry_ids_and_distinct_later_taps():
    from copy import deepcopy

    from apps.channels.ingress import normalize_meta

    payload = {
        "entry": [
            {
                "id": "account",
                "messaging": [
                    {
                        "sender": {"id": "person"},
                        "recipient": {"id": "account"},
                        "timestamp": 12345,
                        "postback": {"title": "Continue", "payload": TOKEN},
                    }
                ],
            }
        ]
    }
    first = list(normalize_meta(payload, "messenger"))
    assert first == list(normalize_meta(payload, "messenger"))
    assert first[0][2]["text"] == TOKEN
    later = deepcopy(payload)
    later["entry"][0]["messaging"][0]["timestamp"] += 1
    assert first[0][1] != list(normalize_meta(later, "messenger"))[0][1]


def test_whatsapp_button_reply_is_normalized_into_the_flow_response():
    from apps.channels.ingress import normalize_meta

    payload = {
        "entry": [
            {
                "id": "business",
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "number"},
                            "messages": [
                                {
                                    "id": "wamid.test",
                                    "from": "person",
                                    "type": "interactive",
                                    "interactive": {
                                        "button_reply": {"id": TOKEN, "title": "Continue"}
                                    },
                                }
                            ],
                        }
                    }
                ],
            }
        ]
    }
    event = list(normalize_meta(payload, "whatsapp"))[0]
    assert event[2]["text"] == TOKEN


def test_whatsapp_mixed_buttons_preserve_links_without_losing_opt_in(channel):
    from apps.channels.providers import WhatsAppAdapter

    adapter = WhatsAppAdapter(channel)
    with patch.object(adapter, "_send", return_value="sent") as send:
        adapter.send_message(
            recipient_id="person",
            text="Continue?",
            idempotency_key="mixed",
            buttons=[
                {"type": "postback", "title": "Continue", "payload": TOKEN},
                {"type": "web_url", "title": "Guide", "url": "https://example.com"},
            ],
        )
    interactive = send.call_args.args[1]["interactive"]
    assert interactive["body"]["text"] == "Continue?\n\nGuide: https://example.com"
    assert interactive["action"]["buttons"][0]["reply"]["id"] == TOKEN


@pytest.mark.parametrize("interactive,limit", [(True, 1024), (False, 4096)])
def test_whatsapp_rejects_overlong_messages_before_provider_call(channel, interactive, limit):
    from apps.channels.providers import ProviderError, WhatsAppAdapter

    adapter = WhatsAppAdapter(channel)
    buttons = [{"type": "postback", "title": "Continue", "payload": TOKEN}] if interactive else []
    with patch.object(adapter, "_send") as send, pytest.raises(ProviderError):
        adapter.send_message(
            recipient_id="person",
            text="x" * (limit + 1),
            idempotency_key="long",
            buttons=buttons,
        )
    send.assert_not_called()


def comment_flow(channel):
    graph = flow(connection=channel, opening=True)
    graph["comment_post_ids"] = ["test-post-1"]
    graph["comment_replies"] = ["Check your messages!", "Sent you the details."]
    return graph


def public_delivery(workspace):
    return next(
        item
        for item in Delivery.objects.for_workspace(workspace)
        if json.loads(item.payload).get("kind") == "public_comment"
    )


def test_post_target_only_matches_selected_account_post(client, workspace, channel):
    assert publish(client, workspace, comment_flow(channel)).status_code == 200
    inbound(channel, "guide", "comment", post_id="test-post-2")
    inbound(channel, "guide", "comment")
    assert not ConversationState.objects.for_workspace(workspace).exists()
    assert not Delivery.objects.for_workspace(workspace).exists()
    inbound(channel, "guide", "comment", post_id="test-post-1")
    state = run(ConversationState.objects.for_workspace(workspace).get())
    assert state.status == "waiting"
    delivery = public_delivery(workspace)
    assert json.loads(delivery.payload)["text"] in comment_flow(channel)["comment_replies"]
    assert Delivery.objects.for_workspace(workspace).count() == 2
    private = next(
        item for item in Delivery.objects.for_workspace(workspace) if item.pk != delivery.pk
    )
    assert json.loads(private.payload)["private_reply"] is True
    from apps.crm.models import Message

    original = Message.objects.for_workspace(workspace).filter(direction="inbound").last()
    assert (
        receive(
            original.event,
            {"sender_id": "person", "kind": "comment", "text": "guide", "post_id": "test-post-1"},
        )
        is None
    )
    assert Delivery.objects.for_workspace(workspace).count() == 2


def test_foreign_post_is_rejected_before_publication(client, workspace, channel):
    graph = comment_flow(channel)
    graph["comment_post_ids"] = ["foreign-post"]
    assert publish(client, workspace, graph).status_code == 400


@pytest.mark.parametrize(
    "key,value",
    [
        ("comment_post_ids", ["../foreign"]),
        ("comment_post_ids", "post-one"),
        ("comment_replies", [""]),
        ("comment_replies", ["x" * 1001]),
        ("comment_replies", ["reply"] * 11),
    ],
)
def test_invalid_comment_settings_fail_validation(client, workspace, channel, key, value):
    graph = comment_flow(channel)
    graph[key] = value
    assert publish(client, workspace, graph).status_code == 400


def test_comment_settings_require_a_bound_comment_trigger(client, workspace, channel):
    graph = comment_flow(channel)
    graph.pop("connection_id")
    assert publish(client, workspace, graph).status_code == 400
    graph["connection_id"] = str(channel.pk)
    graph["triggers"][0]["kind"] = "dm"
    assert publish(client, workspace, graph).status_code == 400


def test_account_posts_are_tenant_scoped(client, workspace, channel):
    path = f"/api/workspaces/{workspace.pk}/connections/{channel.pk}/posts/"
    response = client.get(path)
    assert response.status_code == 200
    assert response.json()["results"][0]["id"] == "test-post-1"
    other_user = User.objects.create_user(username="post-owner", password="test")
    other = create_workspace(other_user, "Other")
    foreign = ChannelConnection.objects.for_workspace(other).create(
        workspace=other,
        external_account_id="other-account",
        access_token="test",
        is_test=True,
        expires_at=timezone.now() + timedelta(days=30),
    )
    assert (
        client.get(f"/api/workspaces/{workspace.pk}/connections/{foreign.pk}/posts/").status_code
        == 404
    )


def test_public_reply_respects_opt_out_at_send_time(client, workspace, channel):
    from apps.channels.tasks import send_delivery

    assert publish(client, workspace, comment_flow(channel)).status_code == 200
    inbound(channel, "guide", "comment", post_id="test-post-1")
    delivery = public_delivery(workspace)
    Lead.objects.for_workspace(workspace).update(opted_out=True)
    with patch("apps.channels.tasks.adapter_for") as adapter:
        send_delivery(str(workspace.pk), str(delivery.pk))
    adapter.assert_not_called()
    delivery.refresh_from_db()
    assert delivery.error_code == "opted_out"


def test_public_reply_is_not_a_dm_and_ambiguous_delivery_is_not_retried(client, workspace, channel):
    from apps.channels.tasks import send_delivery
    from apps.channels.transport import AmbiguousDelivery
    from apps.crm.models import Conversation

    assert publish(client, workspace, comment_flow(channel)).status_code == 200
    inbound(channel, "guide", "comment", post_id="test-post-1")
    delivery = public_delivery(workspace)
    Conversation.objects.for_workspace(workspace).update(
        last_inbound_at=timezone.now() - timedelta(days=2)
    )
    with patch("apps.channels.tasks.adapter_for") as adapter:
        adapter.return_value.reply_comment.side_effect = AmbiguousDelivery()
        send_delivery(str(workspace.pk), str(delivery.pk))
        send_delivery(str(workspace.pk), str(delivery.pk))
        adapter.return_value.reply_comment.assert_called_once()
        adapter.return_value.send_message.assert_not_called()
    delivery.refresh_from_db()
    assert delivery.status == "unknown"


def test_comment_scope_and_public_replies_survive_export_import(client, workspace, channel):
    graph = comment_flow(channel)
    response = publish(client, workspace, graph)
    path = f"/api/workspaces/{workspace.pk}/automations/"
    exported = client.get(f"{path}{response.json()['id']}/export/").json()
    imported = client.post(f"{path}import/", {"template": exported}, format="json")
    assert imported.status_code == 201
    assert imported.json()["draft"]["comment_post_ids"] == graph["comment_post_ids"]
    assert imported.json()["draft"]["comment_replies"] == graph["comment_replies"]


def test_comment_webhooks_keep_post_ids_and_ignore_own_instagram_replies():
    from apps.channels.ingress import normalize_meta

    instagram = {
        "entry": [
            {
                "id": "account",
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "id": "comment",
                            "from": {"id": "person"},
                            "media": {"id": "post"},
                            "text": "guide",
                        },
                    }
                ],
            }
        ]
    }
    assert list(normalize_meta(instagram, "instagram"))[0][2]["post_id"] == "post"
    instagram["entry"][0]["changes"][0]["value"]["from"]["id"] = "account"
    assert list(normalize_meta(instagram, "instagram")) == []
    facebook = {
        "entry": [
            {
                "id": "page",
                "changes": [
                    {
                        "field": "feed",
                        "value": {
                            "item": "comment",
                            "verb": "add",
                            "comment_id": "comment",
                            "post_id": "page_post",
                            "from": {"id": "person"},
                            "message": "guide",
                        },
                    }
                ],
            }
        ]
    }
    assert list(normalize_meta(facebook, "messenger"))[0][2]["post_id"] == "page_post"


@pytest.mark.parametrize("provider,edge", [("instagram", "replies"), ("messenger", "comments")])
def test_public_reply_uses_provider_comment_endpoint(channel, provider, edge):
    from apps.channels.instagram import LiveInstagramAdapter
    from apps.channels.providers import MessengerAdapter

    adapter_type = LiveInstagramAdapter if provider == "instagram" else MessengerAdapter
    module = "apps.channels.instagram" if provider == "instagram" else "apps.channels.providers"
    adapter = adapter_type(channel)
    with patch(f"{module}.request", return_value={"id": "reply-id"}) as send:
        assert (
            adapter.reply_comment(
                comment_id="comment-one", text="Check your messages", idempotency_key="stable"
            )
            == "reply-id"
        )
    assert send.call_args.args[0] == "POST"
    assert send.call_args.args[1].endswith(f"/comment-one/{edge}")
    assert send.call_args.kwargs["side_effect"] is True
    assert send.call_args.kwargs["data"] == {"message": "Check your messages"}


def test_signed_comment_webhook_retries_queue_one_public_reply(
    client, workspace, channel, settings
):
    import hashlib
    import hmac

    from apps.channels.tasks import process_webhook

    settings.META_APP_SECRET = "comment-test-secret"
    assert publish(client, workspace, comment_flow(channel)).status_code == 200
    body = json.dumps(
        {
            "entry": [
                {
                    "id": channel.external_account_id,
                    "changes": [
                        {
                            "field": "comments",
                            "value": {
                                "id": "signed-comment",
                                "media": {"id": "test-post-1"},
                                "from": {"id": "person"},
                                "text": "guide",
                            },
                        }
                    ],
                }
            ]
        }
    ).encode()
    path = "/webhooks/instagram/"
    assert (
        client.post(
            path, body, content_type="application/json", HTTP_X_HUB_SIGNATURE_256="sha256=bad"
        ).status_code
        == 403
    )
    assert not WebhookEvent.objects.for_workspace(workspace).exists()
    signature = (
        "sha256=" + hmac.new(settings.META_APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
    )
    for _ in range(2):
        assert (
            client.post(
                path, body, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=signature
            ).status_code
            == 200
        )
    event = WebhookEvent.objects.for_workspace(workspace).get()
    assert json.loads(event.payload)["post_id"] == "test-post-1"
    process_webhook(str(workspace.pk), str(event.pk))
    process_webhook(str(workspace.pk), str(event.pk))
    assert Delivery.objects.for_workspace(workspace).count() == 1
    assert json.loads(public_delivery(workspace).payload)["kind"] == "public_comment"


def test_public_reply_rate_limit_retries_preserve_the_selected_variation(
    client, workspace, channel
):
    from apps.channels.tasks import send_delivery
    from apps.channels.transport import RetryableError

    assert publish(client, workspace, comment_flow(channel)).status_code == 200
    inbound(channel, "guide", "comment", post_id="test-post-1")
    delivery = public_delivery(workspace)
    with patch("apps.channels.tasks.adapter_for") as adapter:
        adapter.return_value.reply_comment.side_effect = [RetryableError(), "public-id"]
        send_delivery(str(workspace.pk), str(delivery.pk))
        Delivery.objects.for_workspace(workspace).filter(pk=delivery.pk).update(
            available_at=timezone.now()
        )
        send_delivery(str(workspace.pk), str(delivery.pk))
        calls = adapter.return_value.reply_comment.call_args_list
        assert len(calls) == 2 and calls[0] == calls[1]
    delivery.refresh_from_db()
    assert delivery.status == "sent"
    assert delivery.attempts == 2


@pytest.mark.parametrize("provider,owner_field", [("instagram", "owner"), ("messenger", "from")])
def test_post_ownership_is_verified_against_provider_account(channel, provider, owner_field):
    from apps.channels.instagram import LiveInstagramAdapter
    from apps.channels.providers import MessengerAdapter

    adapter_type = LiveInstagramAdapter if provider == "instagram" else MessengerAdapter
    module = "apps.channels.instagram" if provider == "instagram" else "apps.channels.providers"
    adapter = adapter_type(channel)
    with patch(
        f"{module}.request",
        side_effect=[
            {owner_field: {"id": channel.external_account_id}},
            {owner_field: {"id": "foreign"}},
        ],
    ) as read:
        assert adapter.owns_post("post-one") is True
        assert adapter.owns_post("foreign-post") is False
    assert read.call_args.args[0] == "GET"
    assert read.call_args.kwargs["params"]["fields"] == owner_field


def test_field_and_stage_steps_update_the_same_crm_contact(client, workspace, channel):
    graph = flow(
        {"kind": "set_field", "field": "Interest", "value": "Asked about {{last_text}}"},
        {"kind": "set_stage", "stage": "qualified"},
    )
    assert publish(client, workspace, graph).status_code == 200
    inbound(channel, "guide", "comment")
    assert run(ConversationState.objects.for_workspace(workspace).get()).status == "completed"
    lead = Lead.objects.for_workspace(workspace).get()
    assert lead.fields == {"Interest": "Asked about guide"}
    assert lead.stage == "qualified"


@pytest.mark.parametrize(
    "action",
    [
        {"kind": "set_field", "field": "", "value": "test"},
        {"kind": "set_field", "field": "Interest", "value": "x" * 501},
        {"kind": "set_stage", "stage": "invalid"},
        {"kind": "set_stage", "stage": []},
        {"kind": "randomizer", "percentage": -1},
        {"kind": "randomizer", "percentage": 101},
        {"kind": "randomizer", "percentage": True},
        {"kind": "randomizer", "percentage": 2.5},
    ],
)
def test_advanced_action_settings_are_validated(client, workspace, action):
    assert publish(client, workspace, flow(action)).status_code == 400


@pytest.mark.parametrize("existing,expected", [(True, "completed"), (False, "failed")])
def test_field_actions_honor_contact_field_capacity(client, workspace, channel, existing, expected):
    graph = flow(
        {"kind": "set_field", "field": "field-0" if existing else "New field", "value": "updated"}
    )
    assert publish(client, workspace, graph).status_code == 200
    inbound(channel, "guide", "comment")
    Lead.objects.for_workspace(workspace).update(
        fields={f"field-{i}": "original" for i in range(50)}
    )
    assert run(ConversationState.objects.for_workspace(workspace).get()).status == expected
    lead = Lead.objects.for_workspace(workspace).get()
    assert len(lead.fields) == 50
    assert lead.fields["field-0"] == ("updated" if existing else "original")


@pytest.mark.parametrize("percentage,expected", [(0, "B"), (100, "A"), (50, None)])
def test_random_paths_are_weighted_and_stable_on_step_replay(
    client, workspace, channel, percentage, expected
):
    graph = {
        "start": "choose",
        "triggers": [{"kind": "comment", "keyword": "guide"}],
        "nodes": [
            {"id": "choose", "data": {"kind": "randomizer", "percentage": percentage}},
            {"id": "a", "data": {"kind": "add_tag", "tag": "A"}},
            {"id": "b", "data": {"kind": "add_tag", "tag": "B"}},
            {"id": "done", "data": {"kind": "end"}},
        ],
        "edges": [
            {"source": "choose", "target": "a", "sourceHandle": "true"},
            {"source": "choose", "target": "b", "sourceHandle": "false"},
            {"source": "a", "target": "done"},
            {"source": "b", "target": "done"},
        ],
    }
    assert publish(client, workspace, graph).status_code == 200
    inbound(channel, "guide", "comment")
    state = ConversationState.objects.for_workspace(workspace).get()
    step(str(workspace.pk), str(state.pk))
    state.refresh_from_db()
    first_path = state.node_id
    state.node_id = "choose"
    state.steps = 0
    state.save()
    step(str(workspace.pk), str(state.pk))
    state.refresh_from_db()
    assert state.node_id == first_path
    assert run(state).status == "completed"
    tags = Lead.objects.for_workspace(workspace).get().tags
    assert tags == [expected] if expected else tags in (["A"], ["B"])


def next_comment_flow(channel):
    graph = comment_flow(channel)
    graph.pop("comment_post_ids")
    graph["comment_post_mode"] = "next"
    return graph


def test_next_post_activation_uses_server_time_and_clears_imported_resolution(
    client, workspace, channel
):
    from django.utils.dateparse import parse_datetime

    graph = next_comment_flow(channel)
    graph.update(comment_since="2000-01-01T00:00:00+00:00", resolved_next_post_id="foreign-post")
    before = timezone.now()
    response = publish(client, workspace, graph)
    assert response.status_code == 200
    result = response.json()["published"]
    assert parse_datetime(result["comment_since"]) >= before
    assert "resolved_next_post_id" not in result


def test_next_post_is_shared_across_comments_and_does_not_follow_the_latest_post(
    client, workspace, channel
):
    response = publish(client, workspace, next_comment_flow(channel))
    assert response.status_code == 200
    with patch(
        "apps.channels.adapters.FakeChannelAdapter.next_post", return_value="test-post-2"
    ) as lookup:
        inbound(channel, "guide", "comment", post_id="test-post-1")
        assert not ConversationState.objects.for_workspace(workspace).exists()
        inbound(channel, "guide", "comment", post_id="test-post-2")
        inbound(channel, "guide", "comment", post_id="test-post-3", sender_id="another-person")
    lookup.assert_called_once()
    assert ConversationState.objects.for_workspace(workspace).count() == 1
    automation = Automation.objects.for_workspace(workspace).get(pk=response.json()["id"])
    assert automation.published["resolved_next_post_id"] == "test-post-2"
    assert public_delivery(workspace).recipient_id
    republished = client.post(
        f"/api/workspaces/{workspace.pk}/automations/{automation.pk}/publish/",
        {"graph": automation.published},
        format="json",
    )
    assert republished.status_code == 200
    assert "resolved_next_post_id" not in republished.json()["published"]


def test_next_post_remains_armed_when_no_new_post_exists(client, workspace, channel):
    assert publish(client, workspace, next_comment_flow(channel)).status_code == 200
    with patch(
        "apps.channels.adapters.FakeChannelAdapter.next_post", side_effect=[None, "test-post-2"]
    ):
        inbound(channel, "guide", "comment", post_id="test-post-1")
        assert not ConversationState.objects.for_workspace(workspace).exists()
        inbound(channel, "guide", "comment", post_id="test-post-2")
    assert ConversationState.objects.for_workspace(workspace).count() == 1


@pytest.mark.parametrize(
    "provider,timestamp", [("instagram", "timestamp"), ("messenger", "created_time")]
)
def test_next_post_scans_account_pages_and_uses_only_the_returned_cursor(
    channel, provider, timestamp
):
    from apps.channels.instagram import LiveInstagramAdapter
    from apps.channels.providers import MessengerAdapter

    since = timezone.now()

    def post(post_id, minutes):
        return {"id": post_id, timestamp: (since + timedelta(minutes=minutes)).isoformat()}

    pages = [
        {
            "data": [post("third-post", 3), post("second-post", 2)],
            "paging": {
                "next": "https://untrusted.example/never-follow-this",
                "cursors": {"after": "opaque-cursor"},
            },
        },
        {"data": [post("first-post", 1), post("old-post", -1)]},
    ]
    module = "apps.channels.instagram" if provider == "instagram" else "apps.channels.providers"
    adapter = (LiveInstagramAdapter if provider == "instagram" else MessengerAdapter)(channel)
    with patch(f"{module}.request", side_effect=pages) as read:
        assert adapter.next_post(since) == "first-post"
    assert read.call_count == 2
    assert "after" not in read.call_args_list[0].kwargs["params"]
    assert read.call_args_list[1].kwargs["params"]["after"] == "opaque-cursor"
    assert all("untrusted.example" not in call.args[1] for call in read.call_args_list)


def test_next_post_does_not_guess_when_publication_history_is_incomplete():
    from apps.channels.commenting import first_post_after
    from apps.channels.transport import ProviderError

    since = timezone.now()
    page = {
        "data": [{"id": "recent-post", "timestamp": (since + timedelta(minutes=1)).isoformat()}],
        "paging": {"next": "more", "cursors": {"after": "cursor"}},
    }
    with pytest.raises(ProviderError, match="post_history_limit"):
        first_post_after(lambda cursor: page, since, "timestamp")


def test_integration_step_waits_for_durable_job_and_does_not_enqueue_twice(
    client, workspace, channel
):
    from apps.crm.models import IntegrationConfig, IntegrationJob
    from apps.crm.tasks import process_integration
    from tests.conftest import set_limits

    set_limits(workspace, integrations_unlocked=True)
    config = IntegrationConfig.objects.for_workspace(workspace).create(
        workspace=workspace, provider="airtable", is_test=True, credentials="{}"
    )
    graph = flow(
        {
            "kind": "integration_action",
            "integration_id": str(config.pk),
            "operation": "sync_lead",
            "variable": "crm_result",
        }
    )
    assert publish(client, workspace, graph).status_code == 200
    inbound(channel, "guide", "comment")
    state = ConversationState.objects.for_workspace(workspace).get()
    step(str(workspace.pk), str(state.pk))
    step(str(workspace.pk), str(state.pk))
    state.refresh_from_db()
    state.available_at = timezone.now()
    state.save()
    step(str(workspace.pk), str(state.pk))
    assert IntegrationJob.objects.for_workspace(workspace).count() == 1
    job = IntegrationJob.objects.for_workspace(workspace).get()
    process_integration(str(workspace.pk), str(job.pk))
    state.refresh_from_db()
    state.available_at = timezone.now()
    state.save()
    assert run(state).status == "completed"
    assert state.variables["crm_result"]["test"] is True


def test_integration_job_checks_opt_out_before_calling_provider(client, workspace, channel):
    from apps.crm.models import IntegrationConfig, IntegrationJob
    from apps.crm.tasks import process_integration
    from tests.conftest import set_limits

    set_limits(workspace, integrations_unlocked=True)
    config = IntegrationConfig.objects.for_workspace(workspace).create(
        workspace=workspace, provider="slack", is_test=True
    )
    graph = flow(
        {
            "kind": "integration_action",
            "integration_id": str(config.pk),
            "operation": "notify",
            "text": "New lead",
        }
    )
    assert publish(client, workspace, graph).status_code == 200
    inbound(channel, "guide", "comment")
    state = ConversationState.objects.for_workspace(workspace).get()
    step(str(workspace.pk), str(state.pk))
    step(str(workspace.pk), str(state.pk))
    job = IntegrationJob.objects.for_workspace(workspace).get()
    Lead.objects.for_workspace(workspace).update(opted_out=True)
    with patch("apps.crm.tasks.integration_for") as adapter:
        process_integration(str(workspace.pk), str(job.pk))
    adapter.assert_not_called()
    job.refresh_from_db()
    assert job.status == "needs_review"


def test_stale_integration_claims_are_reviewed_without_automatic_replay(workspace):
    from apps.crm.models import IntegrationConfig, IntegrationJob
    from apps.crm.tasks import dispatch_integrations

    config = IntegrationConfig.objects.for_workspace(workspace).create(
        workspace=workspace, provider="slack", is_test=True
    )
    job = IntegrationJob.objects.for_workspace(workspace).create(
        workspace=workspace,
        integration=config,
        operation="notify",
        payload="{}",
        idempotency_key="interrupted",
        status="executing",
        available_at=timezone.now() - timedelta(minutes=10),
    )
    dispatch_integrations()
    job.refresh_from_db()
    assert job.status == "needs_review"
    assert json.loads(job.result)["error"] == "worker_interrupted"


def test_ai_handoff_starts_one_agent_run_and_keeps_future_private_replies_with_ai(
    client, workspace, channel
):
    from apps.agents.models import AgentConfig, AgentRun
    from apps.agents.tasks import process_run
    from tests.conftest import set_limits

    set_limits(workspace, ai_agent_enabled=True)
    AgentConfig.objects.for_workspace(workspace).create(
        workspace=workspace, enabled=True, is_test=True
    )
    graph = {
        "start": "assistant",
        "nodes": [{"id": "assistant", "data": {"kind": "start_agent"}}],
        "edges": [],
        "triggers": [{"kind": "dm", "keyword": "guide"}],
    }
    assert publish(client, workspace, graph).status_code == 200
    inbound(channel, "guide")
    state = ConversationState.objects.for_workspace(workspace).get()
    assert run(state).status == "completed"
    agent_run = AgentRun.objects.for_workspace(workspace).get()
    process_run(str(workspace.pk), str(agent_run.pk))
    agent_run.refresh_from_db()
    assert agent_run.status == "complete"
    inbound(channel, "I have another question")
    assert AgentRun.objects.for_workspace(workspace).count() == 2


def test_ai_handoff_does_not_treat_a_public_comment_as_private_opt_in(client, workspace, channel):
    from apps.agents.models import AgentConfig, AgentRun
    from tests.conftest import set_limits

    set_limits(workspace, ai_agent_enabled=True)
    AgentConfig.objects.for_workspace(workspace).create(
        workspace=workspace, enabled=True, is_test=True
    )
    graph = {
        "start": "assistant",
        "nodes": [{"id": "assistant", "data": {"kind": "start_agent"}}],
        "edges": [],
        "triggers": [{"kind": "comment", "keyword": "guide"}],
    }
    assert publish(client, workspace, graph).status_code == 200
    inbound(channel, "guide", "comment")
    assert run(ConversationState.objects.for_workspace(workspace).get()).status == "failed"
    assert not AgentRun.objects.for_workspace(workspace).exists()


@pytest.mark.parametrize("media_type", ["image", "video", "audio"])
def test_media_waits_for_private_consent_and_queues_once(client, workspace, channel, media_type):
    from apps.crm.views import MessageSerializer

    graph = flow(
        {"kind": "send_media", "media_type": media_type, "media_url": "https://example.com/file"},
        connection=channel,
        opening=True,
    )
    assert publish(client, workspace, graph).status_code == 200
    inbound(channel, "guide", "comment")
    state = run(ConversationState.objects.for_workspace(workspace).get())
    assert state.status == "waiting"
    assert (
        not Delivery.objects.for_workspace(workspace)
        .filter(message__kind__in=["image", "video", "audio"])
        .exists()
    )
    inbound(channel, TOKEN)
    assert run(state).status == "completed"
    media = Delivery.objects.for_workspace(workspace).get(
        message__kind__in=["image", "video", "audio"]
    )
    assert json.loads(media.payload)["media_type"] == media_type
    assert MessageSerializer(media.message).data["media_url"] == "https://example.com/file"
    step(str(workspace.pk), str(state.pk))
    assert (
        Delivery.objects.for_workspace(workspace)
        .filter(message__kind__in=["image", "video", "audio"])
        .count()
        == 1
    )


def test_media_cannot_use_a_public_comment_as_private_consent(client, workspace, channel):
    graph = flow(
        {"kind": "send_media", "media_type": "image", "media_url": "https://example.com/file"},
        connection=channel,
    )
    assert publish(client, workspace, graph).status_code == 200
    inbound(channel, "guide", "comment")
    assert run(ConversationState.objects.for_workspace(workspace).get()).status == "failed"
    assert (
        not Delivery.objects.for_workspace(workspace)
        .filter(message__kind__in=["image", "video", "audio"])
        .exists()
    )


def test_webhook_maps_response_fields_without_replaying_the_request(client, workspace, channel):
    from apps.crm.models import IntegrationConfig, IntegrationJob
    from apps.crm.tasks import process_integration
    from tests.conftest import set_limits

    set_limits(workspace, integrations_unlocked=True)
    config = IntegrationConfig.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider="n8n",
        credentials=json.dumps({"webhook_url": "https://workflow.example/hook"}),
    )
    graph = flow(
        {
            "kind": "integration_action",
            "integration_id": str(config.pk),
            "operation": "webhook",
            "request_body": '{"message":"{{last_text}}"}',
            "response_map": '{"order_id":"order.id"}',
        },
        {"kind": "set_field", "field": "order", "value": "{{order_id}}"},
    )
    assert publish(client, workspace, graph).status_code == 200
    inbound(channel, "guide", "comment")
    state = ConversationState.objects.for_workspace(workspace).get()
    step(str(workspace.pk), str(state.pk))
    step(str(workspace.pk), str(state.pk))
    job = IntegrationJob.objects.for_workspace(workspace).get()
    with patch(
        "apps.public_api.outbound.post_public_json", return_value={"order": {"id": "ord-123"}}
    ) as send:
        process_integration(str(workspace.pk), str(job.pk))
        process_integration(str(workspace.pk), str(job.pk))
    assert send.call_count == 1
    assert send.call_args.args[1] == {"message": "guide"}
    state.available_at = timezone.now()
    state.save()
    assert run(state).status == "completed"
    assert Lead.objects.for_workspace(workspace).get().fields["order"] == "ord-123"


@pytest.mark.parametrize("variable", ["comment_id", "last_text"])
def test_webhook_response_cannot_overwrite_routing_variables(client, workspace, channel, variable):
    graph = flow(
        {
            "kind": "integration_action",
            "integration_id": "11111111-1111-4111-8111-111111111111",
            "operation": "webhook",
            "response_map": {variable: "value"},
        }
    )
    assert publish(client, workspace, graph).status_code == 400


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/a",
        "https://localhost/a",
        "https://127.0.0.1/a",
        "https://[::1]/a",
        "https://user:password@example.com/a",
        "https://example.com/a#token",
        "https://example.com:8000/a",
    ],
)
def test_media_rejects_nonpublic_or_credential_bearing_urls(client, workspace, channel, url):
    graph = flow(
        {"kind": "send_media", "media_type": "image", "media_url": url}, connection=channel
    )
    assert publish(client, workspace, graph).status_code == 400


@pytest.mark.parametrize("provider", ["instagram", "messenger", "whatsapp", "telegram"])
@pytest.mark.parametrize("media_type", ["image", "video", "audio"])
def test_media_provider_payloads(channel, provider, media_type):
    from apps.channels.instagram import LiveInstagramAdapter
    from apps.channels.providers import MessengerAdapter, TelegramAdapter, WhatsAppAdapter

    cls = {
        "instagram": LiveInstagramAdapter,
        "messenger": MessengerAdapter,
        "whatsapp": WhatsAppAdapter,
        "telegram": TelegramAdapter,
    }[provider]
    adapter = cls(channel)
    response = {
        "message_id": "sent",
        "messages": [{"id": "sent"}],
        "ok": True,
        "result": {"message_id": "sent"},
    }
    with (
        patch("apps.channels.instagram.request", return_value=response) as instagram,
        patch("apps.channels.providers.request", return_value=response) as others,
    ):
        assert (
            adapter.send_media(
                recipient_id="person",
                media_url="https://example.com/file",
                media_type=media_type,
                idempotency_key="media",
            )
            == "sent"
        )
    call = (instagram if provider == "instagram" else others).call_args
    body = call.kwargs["json"]
    if provider in {"instagram", "messenger"}:
        assert body["recipient"] == {"id": "person"}
        assert body["message"]["attachment"]["type"] == media_type
        assert body["message"]["attachment"]["payload"]["url"] == "https://example.com/file"
    elif provider == "whatsapp":
        assert body["type"] == media_type and body[media_type]["link"] == "https://example.com/file"
    else:
        method, field = {
            "image": ("sendPhoto", "photo"),
            "video": ("sendVideo", "video"),
            "audio": ("sendAudio", "audio"),
        }[media_type]
        assert call.args[1].endswith("/" + method)
        assert body[field] == "https://example.com/file"

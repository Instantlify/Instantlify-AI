import json

import pytest
from rest_framework.test import APIClient

from apps.channels.models import Delivery
from apps.crm.models import Conversation
from apps.crm.services import queue_reply

pytestmark = pytest.mark.django_db


def test_appearance_settings_round_trip_and_reach_the_widget(client, workspace):
    url = f"/api/workspaces/{workspace.pk}/webchat/"
    res = client.put(
        url,
        {
            "title": "Help",
            "greeting": "Hi!",
            "color": "#112233",
            "position": "left",
            "launcher_label": "Ask us",
            "logo_url": "https://cdn.example.com/logo.png",
            "quick_replies": ["Prices?", " Prices? ", "Book a call"],
        },
        format="json",
    )
    assert res.status_code == 200, res.content
    assert res.json()["quick_replies"] == ["Prices?", "Book a call"]
    public = APIClient().get(f"/api/public/webchat/{workspace.pk}/").json()
    assert (public["position"], public["launcher_label"]) == ("left", "Ask us")
    assert public["logo_url"] == "https://cdn.example.com/logo.png"
    assert public["quick_replies"] == ["Prices?", "Book a call"]


@pytest.mark.parametrize(
    "body",
    [
        {"position": "top"},
        {"logo_url": "http://insecure.example.com/logo.png"},
        {"quick_replies": ["a", "b", "c", "d", "e", "f"]},
        {"quick_replies": ["x" * 41]},
    ],
)
def test_invalid_appearance(client, workspace, body):
    url = f"/api/workspaces/{workspace.pk}/webchat/"
    payload = {"title": "Help", "greeting": "Hi", "color": "#112233", **body}
    assert client.put(url, payload, format="json").status_code == 400


def test_automation_buttons_are_shown_to_the_visitor(workspace, settings):
    settings.CHANNEL_ADAPTER_MODE = "fake"
    visitor = APIClient()
    url = f"/api/public/webchat/{workspace.pk}/"
    visitor.post(url, {"visitor": "visitor-abc123", "text": "hi"}, format="json")
    conversation = Conversation.objects.for_workspace(workspace).get()
    queue_reply(
        conversation,
        "Pick one",
        "flow-buttons",
        buttons=[
            {"type": "web_url", "title": "Pricing", "url": "https://example.com/pricing"},
            {"type": "postback", "title": "Talk to us", "payload": "talk"},
            {"type": "web_url", "title": "Bad", "url": "javascript:alert(1)"},
        ],
    )
    assert json.loads(Delivery.objects.for_workspace(workspace).get().payload)["buttons"]
    messages = visitor.get(url, {"visitor": "visitor-abc123"}).json()["messages"]
    assert messages[-1]["buttons"] == [
        {"title": "Pricing", "url": "https://example.com/pricing"},
        {"title": "Talk to us", "payload": "talk"},
    ]
    assert messages[0]["buttons"] == []

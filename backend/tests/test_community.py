import json
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.crm.models import Lead
from apps.platform_ops.models import CommunityPost, CommunityReply, CommunityVote, PlatformAudit
from apps.tenants.models import User

pytestmark = pytest.mark.django_db


def second_user():
    user = User.objects.create_user(
        username="other",
        email="private-other@example.com",
        password="example-password",
        first_name="Second",
    )
    client = APIClient()
    client.force_authenticate(user)
    return user, client


def post(client, text="How do keyword automations work?"):
    response = client.post("/api/community/", {"body": text}, format="json")
    assert response.status_code == 201, response.content
    return response.json()


def test_community_requires_authentication_and_does_not_expose_private_identifiers(client, user):
    assert APIClient().get("/api/community/").status_code == 403
    item = post(client)
    assert item["can_edit"] and not item["can_pin"]
    assert user.email not in json.dumps(item) and "workspace" not in item
    _, other = second_user()
    feed = other.get("/api/community/").json()
    assert feed["count"] == 1 and feed["results"][0]["id"] == item["id"]
    assert not feed["results"][0]["can_edit"]


def test_only_author_can_edit_and_only_moderator_can_pin(client, user):
    item = post(client)
    url = f"/api/community/{item['id']}/"
    _, other = second_user()
    assert other.patch(url, {"body": "Hijacked"}, format="json").status_code == 403
    assert other.delete(url).status_code == 403
    assert client.patch(url, {"pinned": True}, format="json").status_code == 403
    assert client.patch(url, {"body": "Edited"}, format="json").json()["body"] == "Edited"
    user.is_superuser = True
    user.save(update_fields=["is_superuser"])
    assert client.patch(url, {"pinned": True}, format="json").json()["pinned"] is True
    assert PlatformAudit.objects.filter(action="community.pin").count() == 1
    assert client.delete(url).status_code == 204


def test_reactions_are_unique_retry_safe_and_can_switch_or_be_removed(client, user):
    item = post(client)
    url = f"/api/community/{item['id']}/reaction/"
    for _ in range(2):
        assert client.post(url, {"value": 1}, format="json").json()["likes"] == 1
    switched = client.post(url, {"value": -1}, format="json").json()
    assert switched["likes"] == 0 and switched["dislikes"] == 1
    assert CommunityVote.objects.filter(author=user).count() == 1
    assert client.post(url, {"value": True}, format="json").status_code == 400
    assert client.post(url, {"value": 0}, format="json").json()["my_vote"] == 0
    assert not CommunityVote.objects.exists()


def test_threaded_replies_are_editable_only_by_their_author_or_moderator(client):
    item = post(client)
    _, other = second_user()
    url = f"/api/community/{item['id']}/replies/"
    reply = other.post(url, {"body": "A useful reply"}, format="json").json()
    assert client.get(url).json()["results"][0]["body"] == "A useful reply"
    assert client.delete(url + reply["id"] + "/").status_code == 403
    assert other.delete(url + reply["id"] + "/").status_code == 204


def test_nested_replies_stay_in_their_discussion_and_survive_parent_deletion(client):
    first, second = post(client), post(client, "Another discussion")
    url = f"/api/community/{first['id']}/replies/"
    parent = client.post(url, {"body": "Parent"}, format="json").json()
    child = client.post(url, {"body": "Child", "parent_id": parent["id"]}, format="json")
    assert child.status_code == 201 and child.json()["parent_id"] == parent["id"]
    assert (
        client.post(
            f"/api/community/{second['id']}/replies/",
            {"body": "Wrong thread", "parent_id": parent["id"]},
            format="json",
        ).status_code
        == 404
    )
    assert client.delete(url + parent["id"] + "/").status_code == 204
    remaining = client.get(url).json()["results"]
    assert len(remaining) == 1 and remaining[0]["parent_id"] is None


def test_assistant_only_uses_shared_discussions_and_reports_sources(client, workspace):
    Lead.objects.for_workspace(workspace).create(
        workspace=workspace, name="Private Saffron Secret", fields={"secret": "never share"}
    )
    with patch("apps.platform_ops.intelligence.complete") as complete:
        result = client.post(
            "/api/community/assistant/", {"question": "Saffron secret"}, format="json"
        ).json()
        assert not result["sources"]
        complete.assert_not_called()
    item = post(client, "Keyword automations match incoming comments to a published workflow.")
    result = client.post(
        "/api/community/assistant/", {"question": "keyword workflow"}, format="json"
    ).json()
    assert result["sources"][0]["post_id"] == item["id"]
    assert "Private Saffron" not in json.dumps(result)


def test_personal_export_only_contains_own_contributions(client, user):
    mine = post(client)
    other_user, other = second_user()
    theirs = post(other, "Someone else's discussion")
    CommunityReply.objects.create(post_id=theirs["id"], author=user, body="My reply")
    data = json.loads(b"".join(client.get("/api/community/me/export/").streaming_content))
    assert [item["id"] for item in data["posts"]] == [mine["id"]]
    assert data["replies"][0]["body"] == "My reply"
    assert other_user.email not in json.dumps(data)


def test_feed_pagination_and_empty_messages_are_validated(client, user):
    CommunityPost.objects.bulk_create(
        [CommunityPost(author=user, body=f"Post {i}") for i in range(31)]
    )
    assert len(client.get("/api/community/").json()["results"]) == 30
    assert len(client.get("/api/community/?page=2").json()["results"]) == 1
    assert client.get("/api/community/?page=invalid").status_code == 400
    assert client.post("/api/community/", {"body": "  "}, format="json").status_code == 400

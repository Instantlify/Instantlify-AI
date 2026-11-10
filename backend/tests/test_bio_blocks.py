import pytest
from rest_framework.test import APIClient

from apps.content.bio_blocks import embed_url
from apps.crm.models import Lead
from tests.conftest import set_limits

pytestmark = pytest.mark.django_db

BLOCKS = [
    {"type": "heading", "text": "Hi, I'm Ada"},
    {"type": "text", "text": "I teach analytics."},
    {"type": "link", "title": "Book a call", "url": "https://cal.com/ada", "highlight": True},
    {
        "type": "image",
        "url": "https://cdn.example.com/a.png",
        "alt": "Me",
        "link": "https://ada.dev",
    },
    {"type": "video", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
    {"type": "social", "items": [{"platform": "instagram", "url": "https://instagram.com/ada"}]},
    {"type": "email_capture", "title": "Get my newsletter", "button": "Join", "tag": "newsletter"},
    {"type": "divider"},
]


def save(client, workspace, **extra):
    return client.put(
        f"/api/workspaces/{workspace.pk}/bio/",
        {
            "slug": "ada",
            "title": "Ada",
            "blocks": BLOCKS,
            "theme": "dark",
            "published": True,
            **extra,
        },
        format="json",
    )


def test_blocks_render_publicly_and_track_clicks(client, workspace):
    res = save(client, workspace)
    assert res.status_code == 200, res.content
    assert res.json()["blocks"][4]["embed"] == "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"
    visitor = APIClient()
    page = visitor.get("/api/public/bio/ada/").json()
    assert page["theme"] == "dark" and len(page["blocks"]) == 8
    assert "tag" not in page["blocks"][6]  # internal tag is not exposed
    assert visitor.post("/api/public/bio/ada/", {"block": 2}, format="json").json() == {
        "url": "https://cal.com/ada"
    }
    assert visitor.post("/api/public/bio/ada/", {"block": 3}, format="json").json()["url"] == (
        "https://ada.dev"
    )
    assert (
        visitor.post("/api/public/bio/ada/", {"block": 5, "item": 0}, format="json").json()["url"]
        == "https://instagram.com/ada"
    )
    assert visitor.post("/api/public/bio/ada/", {"block": 0}, format="json").status_code == 404


def test_email_signup_creates_or_tags_contacts(client, workspace):
    save(client, workspace)
    visitor = APIClient()
    url = "/api/public/bio/ada/"
    assert (
        visitor.post(
            url, {"block": 6, "email": "Fan@Example.com", "name": "Fan"}, format="json"
        ).status_code
        == 201
    )
    lead = Lead.objects.for_workspace(workspace).get(email="fan@example.com")
    assert lead.tags == ["newsletter"] and lead.fields == {"source": "bio"}
    assert (
        visitor.post(url, {"block": 6, "email": "fan@example.com"}, format="json").status_code
        == 201
    )
    assert Lead.objects.for_workspace(workspace).count() == 1
    assert visitor.post(url, {"block": 6, "email": "nope"}, format="json").status_code == 400
    assert visitor.post(url, {"block": 2, "email": "a@b.com"}, format="json").status_code == 404
    set_limits(workspace, max_contacts=1)
    assert (
        visitor.post(url, {"block": 6, "email": "new@example.com"}, format="json").status_code
        == 503
    )


@pytest.mark.parametrize(
    "block",
    [
        {"type": "link", "title": "x", "url": "http://insecure.com"},
        {"type": "video", "url": "https://evil.example.com/video"},
        {"type": "social", "items": [{"platform": "myspace", "url": "https://myspace.com/a"}]},
        {"type": "image", "url": "javascript:alert(1)"},
        {"type": "script"},
    ],
)
def test_invalid_blocks_are_rejected(client, workspace, block):
    assert save(client, workspace, blocks=[block]).status_code == 400


def test_embed_urls():
    assert (
        embed_url("https://youtu.be/abcdefghijk")
        == "https://www.youtube-nocookie.com/embed/abcdefghijk"
    )
    assert embed_url("https://vimeo.com/123456") == "https://player.vimeo.com/video/123456"
    assert embed_url("https://www.loom.com/share/0123456789abcdef0123") == (
        "https://www.loom.com/embed/0123456789abcdef0123"
    )
    assert embed_url("https://example.com/watch?v=abc") is None

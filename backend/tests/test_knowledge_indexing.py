from unittest.mock import patch

import pytest
from django.core.cache import cache

from apps.channels.transport import ProviderError
from apps.platform_ops.knowledge_indexing import LOCK_KEY, enqueue, status
from apps.platform_ops.models import PlatformKnowledgeDocument, PlatformKnowledgeSection
from apps.platform_ops.tasks import embed_platform_knowledge
from tests.test_workspace_capabilities import console  # noqa: F401

pytestmark = pytest.mark.django_db


def section():
    document = PlatformKnowledgeDocument.objects.create(title="Support")
    return PlatformKnowledgeSection.objects.create(
        document=document, title="About", body_markdown="Nemio support"
    )


def test_provider_failure_is_visible_without_losing_sections():
    item = section()
    with patch(
        "apps.platform_ops.intelligence.embed", side_effect=ProviderError("provider_rejected")
    ):
        with pytest.raises(ProviderError):
            embed_platform_knowledge()
    assert status()["state"] == "failed"
    assert "text-embedding-3-small" in status()["message"]
    item.refresh_from_db()
    assert item.embedding is None
    assert item.body_markdown == "Nemio support"


def test_success_updates_status_and_sections():
    item = section()
    with patch("apps.platform_ops.intelligence.embed", return_value=([[0.1] * 1536], 3)):
        assert embed_platform_knowledge() == 1
    item.refresh_from_db()
    assert item.embedded_at is not None
    assert status()["state"] == "succeeded"


def test_incomplete_response_never_marks_document_embedded():
    item = section()
    with patch("apps.platform_ops.intelligence.embed", return_value=([], 0)):
        with pytest.raises(ProviderError):
            embed_platform_knowledge()
    item.document.refresh_from_db()
    assert item.document.embedded_at is None
    assert status()["state"] == "failed"


def test_duplicate_clicks_queue_only_one_job():
    with patch.object(embed_platform_knowledge, "delay") as delay:
        enqueue()
        enqueue()
    delay.assert_called_once()
    assert status()["state"] == "queued"
    cache.delete(LOCK_KEY)
    assert status()["state"] == "failed"


def test_queue_failure_is_visible_and_retryable():
    with patch.object(
        embed_platform_knowledge, "delay", side_effect=RuntimeError("Private details")
    ):
        enqueue()
    assert status()["state"] == "failed"
    assert "Private details" not in status()["message"]
    assert cache.get(LOCK_KEY) is None


def test_console_queues_after_commit_and_exposes_status(
    request, django_capture_on_commit_callbacks
):
    client, _ = request.getfixturevalue("console")
    with patch.object(embed_platform_knowledge, "delay") as delay:
        with django_capture_on_commit_callbacks(execute=True):
            response = client.post("/ops/knowledge/", {"action": "reembed"})
    assert response.status_code == 302
    delay.assert_called_once()
    response = client.get("/ops/knowledge/status/")
    assert response.json()["state"] == "queued"
    assert "no-store" in response["Cache-Control"]
    page = client.get("/ops/?tab=agent_config")
    assert b"Re-embedding queued" in page.content
    import re

    nonce = re.search(r'<script nonce="([^"]+)"', page.content.decode()).group(1)
    policy = page["Content-Security-Policy"]
    assert f"script-src 'self' 'nonce-{nonce}'" in policy
    assert "unsafe-inline" not in policy.split("script-src ")[1].split(";")[0]
    next_page = client.get("/ops/?tab=agent_config")
    assert f"nonce-{nonce}" not in next_page["Content-Security-Policy"]


def test_status_requires_console_mfa(request):
    client, _ = request.getfixturevalue("console")
    session = client.session
    session.pop("platform_mfa")
    session.save()
    assert client.get("/ops/knowledge/status/").url == "/ops/mfa/"

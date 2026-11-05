from unittest.mock import patch

import pytest

from apps.platform_ops import intelligence, support_agent
from apps.platform_ops.models import PlatformKnowledgeDocument, PlatformKnowledgeSection

pytestmark = pytest.mark.django_db


def test_openai_health_check_uses_configured_platform_model(settings):
    settings.CHANNEL_ADAPTER_MODE = "live"
    settings.PLATFORM_OPENAI_API_KEY = "test-only-key"
    settings.PLATFORM_AI_MODEL = "gpt-4.1-mini"
    with patch("apps.platform_ops.intelligence.request", return_value={}) as request:
        result = intelligence.ping("PLATFORM_OPENAI_API_KEY")
    assert result["ok"] is True
    assert request.call_args.kwargs["json"]["model"] == "gpt-4.1-mini"


def test_gemini_health_check_uses_configured_model(settings, monkeypatch):
    settings.CHANNEL_ADAPTER_MODE = "live"
    settings.PLATFORM_GEMINI_MODEL = "gemini-current-model"
    monkeypatch.setenv("PLATFORM_GEMINI_API_KEY", "test-only-key")
    with patch("apps.platform_ops.intelligence.request", return_value={}) as request:
        result = intelligence.ping("PLATFORM_GEMINI_API_KEY")
    assert result["ok"] is True
    assert request.call_args.args[1].endswith("/gemini-current-model:generateContent")


def test_empty_knowledge_base_does_not_require_embeddings():
    with patch("apps.platform_ops.intelligence.embed") as embed:
        assert intelligence.retrieve_sections("Hi") == []
    embed.assert_not_called()


def test_unindexed_sections_do_not_require_embeddings():
    document = PlatformKnowledgeDocument.objects.create(title="Help")
    PlatformKnowledgeSection.objects.create(document=document, title="Intro", body_markdown="Hello")
    with patch("apps.platform_ops.intelligence.embed") as embed:
        assert intelligence.retrieve_sections("Hi") == []
    embed.assert_not_called()


def test_support_uses_configured_model_without_knowledge(settings):
    settings.CHANNEL_ADAPTER_MODE = "live"
    settings.PLATFORM_OPENAI_API_KEY = "test-only-key"
    settings.PLATFORM_AI_MODEL = "gpt-4.1-mini"
    response = {
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "Hello! How can I help?"}],
            }
        ]
    }
    with patch("apps.platform_ops.intelligence.request", return_value=response) as request:
        result = support_agent.answer("Hi")
    request.assert_called_once()
    assert request.call_args.kwargs["json"]["model"] == "gpt-4.1-mini"
    assert result["reply"] == "Hello! How can I help?"

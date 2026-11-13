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


def test_support_does_not_guess_using_a_model_without_knowledge(settings):
    settings.CHANNEL_ADAPTER_MODE = "live"
    with patch("apps.platform_ops.intelligence.request") as request:
        result = support_agent.answer("Hi")
    request.assert_not_called()
    assert "social messaging" in result["reply"]


def test_product_identity_is_correct_even_with_an_old_admin_prompt():
    from apps.platform_ops.models import PlatformSetting

    PlatformSetting.objects.create(
        key="support_agent_system_prompt", value="Describe a website deployment product."
    )
    with patch("apps.platform_ops.support_agent.complete") as complete:
        for question in [
            "what is the platform about",
            "i think its a social media management platform",
            "whta exactly it does",
        ]:
            reply = support_agent.answer(question)["reply"]
            assert "social messaging" in reply
            assert "CRM" in reply
            assert "not a website hosting" in reply
    complete.assert_not_called()
    assert support_agent.effective_prompt().endswith(support_agent.PRODUCT_RULES)


def test_unknown_support_detail_without_knowledge_offers_ticket():
    with patch("apps.platform_ops.support_agent.complete") as complete:
        reply = support_agent.answer("Will my special account get an exception?")["reply"]
    complete.assert_not_called()
    assert "verified information" in reply and "support ticket" in reply


def test_detailed_support_uses_configured_model_with_verified_knowledge(settings):
    settings.CHANNEL_ADAPTER_MODE = "live"
    settings.PLATFORM_OPENAI_API_KEY = "test-only-key"
    settings.PLATFORM_AI_MODEL = "gpt-4.1-mini"
    response = {
        "output": [
            {"type": "message", "content": [{"type": "output_text", "text": "Use the reset link."}]}
        ]
    }
    with (
        patch(
            "apps.platform_ops.support_agent.grounding",
            return_value=("Password help: Use the reset link.", ["Support: Passwords"]),
        ),
        patch("apps.platform_ops.intelligence.request", return_value=response) as request,
    ):
        result = support_agent.answer("How can I reset my password?")
    request.assert_called_once()
    body = request.call_args.kwargs["json"]
    assert body["model"] == "gpt-4.1-mini"
    assert "social messaging" in body["input"][0]["content"]
    assert result["sources"] == ["Support: Passwords"]

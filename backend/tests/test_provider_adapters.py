"""Anthropic, Gemini and xAI adapters: request translation, response parsing, fallback
and billing. HTTP is stubbed at `providers.request`; shapes follow each vendor's API."""

import json
from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.agents.models import AgentConfig
from apps.agents.providers import (
    AnthropicProvider,
    Completion,
    FallbackProvider,
    GeminiProvider,
    OpenAIProvider,
    XAIProvider,
    embedder_for,
    provider_for,
)
from apps.agents.tools import definitions
from apps.channels.transport import ProviderError, RetryableError

pytestmark = pytest.mark.django_db

TOOLS = definitions(["check_calendar_availability"])
# One full tool round in the runtime's shape: instructions, customer turns, a call and
# its result. The instructions sit first here and last in the triage call.
HISTORY = [
    {"role": "developer", "content": "Be brief."},
    {"role": "assistant", "content": "Hi! Thanks for the follow."},
    {"role": "user", "content": "Any slots tomorrow?"},
    {
        "type": "function_call",
        "call_id": "toolu_1",
        "name": "check_calendar_availability",
        "arguments": json.dumps({"start": "2026-09-19T09:00", "end": "2026-09-19T17:00"}),
    },
    {"type": "function_call_output", "call_id": "toolu_1", "output": '{"slots": ["10:00"]}'},
]


@pytest.fixture
def config(workspace, settings):
    settings.PLATFORM_ANTHROPIC_API_KEY = "sk-ant"
    settings.PLATFORM_GEMINI_API_KEY = "g-key"
    settings.PLATFORM_XAI_API_KEY = "xai-key"
    settings.PLATFORM_OPENAI_API_KEY = "sk-openai"
    return AgentConfig.objects.for_workspace(workspace).create(
        workspace=workspace, enabled=True, provider="anthropic", model="claude-sonnet-5"
    )


def call(provider, response, messages=HISTORY, tools=TOOLS):
    with patch("apps.agents.providers.request", return_value=response) as request:
        completion = provider.complete(messages, tools)
    (method, url), kwargs = request.call_args
    return completion, url, kwargs["headers"], kwargs["json"]


# --- Anthropic


def test_anthropic_translates_history_and_parses_tool_use(config):
    completion, url, headers, body = call(
        AnthropicProvider(config),
        {
            "content": [
                {"type": "text", "text": "Let me check."},
                {
                    "type": "tool_use",
                    "id": "toolu_2",
                    "name": "check_calendar_availability",
                    "input": {"start": "a", "end": "b"},
                },
            ],
            "usage": {"input_tokens": 100, "output_tokens": 20, "cache_read_input_tokens": 5},
        },
    )
    assert url == "https://api.anthropic.com/v1/messages"
    assert headers == {"x-api-key": "sk-ant", "anthropic-version": "2023-06-01"}
    assert body["model"] == "claude-sonnet-5" and body["system"] == "Be brief."
    roles = [m["role"] for m in body["messages"]]
    # Opens on the customer, alternates, and the tool result follows its call.
    assert roles == ["user", "assistant", "user", "assistant", "user"]
    assert body["messages"][3]["content"][0] == {
        "type": "tool_use",
        "id": "toolu_1",
        "name": "check_calendar_availability",
        "input": {"start": "2026-09-19T09:00", "end": "2026-09-19T17:00"},
    }
    assert body["messages"][4]["content"][0]["type"] == "tool_result"
    assert body["tools"][0]["input_schema"]["required"] == ["start", "end"]
    assert completion == Completion(
        "Let me check.",
        [
            {
                "name": "check_calendar_availability",
                "arguments": '{"start": "a", "end": "b"}',
                "call_id": "toolu_2",
            }
        ],
        105,
        20,
        "claude-sonnet-5",
    )


def test_anthropic_triage_call_moves_trailing_instructions_to_system(config):
    _, _, _, body = call(
        AnthropicProvider(config),
        {"content": [{"type": "text", "text": "{}"}], "usage": {}},
        messages=[{"role": "user", "content": "hi"}, {"role": "developer", "content": "Classify"}],
        tools=[],
    )
    assert body["system"] == "Classify" and "tools" not in body
    assert body["messages"] == [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]


# --- Gemini


def test_gemini_round_trips_thought_signatures_and_strips_schema(config):
    config.provider, config.model = "gemini", "gemini-pro-latest"
    completion, url, headers, body = call(
        GeminiProvider(config),
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "thinking…", "thought": True},
                            {
                                "functionCall": {
                                    "name": "check_calendar_availability",
                                    "args": {"start": "x"},
                                },
                                "thoughtSignature": "abc123",
                            },
                        ]
                    }
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 50,
                "candidatesTokenCount": 10,
                "thoughtsTokenCount": 30,
            },
        },
    )
    assert url.endswith("/models/gemini-pro-latest:generateContent")
    assert headers == {"x-goog-api-key": "g-key"}
    assert body["systemInstruction"] == {"parts": [{"text": "Be brief."}]}
    declaration = body["tools"][0]["functionDeclarations"][0]
    assert "additionalProperties" not in declaration["parameters"]
    assert "strict" not in json.dumps(declaration)
    # The function response carries the name of the call it answers.
    assert (
        body["contents"][-1]["parts"][0]["functionResponse"]["name"]
        == "check_calendar_availability"
    )
    # Thoughts are not reply text; thinking tokens are billed as output.
    assert completion.text == "" and completion.output_tokens == 40
    [made] = completion.calls
    assert made["call_id"] == "sig:abc123"
    # Sent back next round, the signature returns to the part it came from.
    history = [
        {"role": "user", "content": "hi"},
        {"type": "function_call", **made},
        {"type": "function_call_output", "call_id": made["call_id"], "output": "[1, 2]"},
    ]
    converted = GeminiProvider.convert(history, [])
    call_part = converted["contents"][1]["parts"][0]
    assert call_part["thoughtSignature"] == "abc123"
    result = converted["contents"][2]["parts"][0]["functionResponse"]
    assert result["response"] == {"result": [1, 2]}  # non-object output is wrapped


# --- xAI


def test_xai_uses_chat_completions_with_tool_messages(config):
    config.provider, config.model = "xai", "grok-latest"
    completion, url, headers, body = call(
        XAIProvider(config),
        {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_9",
                                "type": "function",
                                "function": {
                                    "name": "check_calendar_availability",
                                    "arguments": '{"start":"a","end":"b"}',
                                },
                            }
                        ],
                    }
                }
            ],
            "usage": {"prompt_tokens": 70, "completion_tokens": 9},
        },
    )
    assert url == "https://api.x.ai/v1/chat/completions"
    assert headers == {"Authorization": "Bearer xai-key"}
    assert body["messages"][0] == {"role": "system", "content": "Be brief."}
    assert body["messages"][3]["tool_calls"][0]["id"] == "toolu_1"
    assert body["messages"][4] == {
        "role": "tool",
        "tool_call_id": "toolu_1",
        "content": '{"slots": ["10:00"]}',
    }
    assert body["tools"][0]["function"]["name"] == "check_calendar_availability"
    assert completion.calls[0]["call_id"] == "call_9" and completion.text == ""
    assert (completion.input_tokens, completion.output_tokens) == (70, 9)


# --- selection, keys, fallback


def test_provider_selection_and_keys(config, settings):
    assert isinstance(provider_for(config), AnthropicProvider)
    config.provider = "nope"
    with pytest.raises(ProviderError, match="unsupported_llm_provider"):
        provider_for(config)
    config.provider = "gemini"
    settings.PLATFORM_GEMINI_API_KEY = ""
    with pytest.raises(ProviderError, match="platform_llm_key_missing"):
        provider_for(config)


def test_fallback_on_rate_limit_is_billed_at_the_answering_model(config, workspace):
    from apps.agents.models import UsageRecord
    from apps.billing import credits
    from apps.billing.models import AICreditTransaction, ModelPricingRate
    from apps.billing.services import complete_usage, reserve_usage

    config.fallback_provider, config.fallback_model = "openai", "gpt-5.4-mini"
    config.save()
    provider = provider_for(config)
    assert isinstance(provider, FallbackProvider)
    assert isinstance(provider.secondary, OpenAIProvider)
    assert provider.secondary.model == "gpt-5.4-mini"
    answer = Completion("from openai", [], 1_000_000, 0, "gpt-5.4-mini")
    with (
        patch.object(provider.primary, "complete", side_effect=RetryableError(30)),
        patch.object(provider.secondary, "complete", return_value=answer),
    ):
        completion = provider.complete(HISTORY, [])
    assert completion.text == "from openai"
    credits.credit(workspace.pk, key="seed", amount_cents=1000, type="adjustment")
    record = reserve_usage(config, "turn")
    complete_usage(record, completion, config)
    row = AICreditTransaction.objects.for_workspace(workspace).get(type="usage")
    # Seeded gpt-5.4-mini input rate (60 cents/M), not the Claude fallback rate.
    assert row.model == "gpt-5.4-mini" and row.amount_cents == Decimal("-60")
    assert row.rate == ModelPricingRate.objects.get(model_pattern="gpt-5.4-mini")
    assert UsageRecord.objects.for_workspace(workspace).get(pk=record.pk).calls == 1


def test_non_retryable_errors_do_not_fall_back(config):
    config.fallback_provider, config.fallback_model = "openai", "gpt-5.4-mini"
    provider = provider_for(config)
    with (
        patch.object(provider.primary, "complete", side_effect=ProviderError("bad_request")),
        patch.object(provider.secondary, "complete") as secondary,
        pytest.raises(ProviderError, match="bad_request"),
    ):
        provider.complete(HISTORY, [])
    secondary.assert_not_called()


def test_byo_key_never_falls_back_to_platform_keys(config):
    config.billing_mode, config.api_key = "byo_key", "sk-ant-own"
    config.fallback_provider, config.fallback_model = "openai", "gpt-5.4-mini"
    provider = provider_for(config)
    assert isinstance(provider, AnthropicProvider)
    assert provider.headers["x-api-key"] == "sk-ant-own"


def test_embeddings_always_use_openai(config):
    platform = embedder_for(config)
    assert isinstance(platform, OpenAIProvider)
    assert platform.headers["Authorization"] == "Bearer sk-openai"
    config.billing_mode, config.api_key = "byo_key", "sk-ant-own"
    with pytest.raises(ProviderError, match="embedding_key_missing"):
        embedder_for(config)
    config.embedding_api_key = "sk-openai-own"
    assert embedder_for(config).headers["Authorization"] == "Bearer sk-openai-own"


def test_settings_api_validates_providers_and_fallbacks(client, workspace, config):
    url = f"/api/workspaces/{workspace.pk}/agent/"
    ok = client.put(url, {"provider": "xai", "model": "grok-latest"}, format="json")
    assert ok.status_code == 200 and ok.json()["provider"] == "xai"
    assert client.put(url, {"provider": "mistral"}, format="json").status_code == 400
    same = {"fallback_provider": "xai", "fallback_model": "grok-latest"}
    assert client.put(url, same, format="json").status_code == 400
    no_model = {"fallback_provider": "openai", "fallback_model": ""}
    assert client.put(url, no_model, format="json").status_code == 400
    byo = {"billing_mode": "byo_key", "fallback_provider": "openai", "fallback_model": "m"}
    assert client.put(url, byo, format="json").status_code == 400
    saved = client.put(url, {"embedding_api_key": "sk-embed"}, format="json").json()
    assert saved["has_embedding_key"] and "embedding_api_key" not in saved
    client.put(url, {"embedding_api_key": ""}, format="json")  # blank keeps the key
    config.refresh_from_db()
    assert config.embedding_api_key == "sk-embed"


def test_platform_models_catalog_and_endpoint(client, workspace, config):
    # Test catalog function
    from apps.agents.catalog import get_platform_models

    models = get_platform_models()
    assert len(models) >= 4
    model_ids = [m["id"] for m in models]
    assert "gpt-5.4-mini" in model_ids
    assert "claude-sonnet-5" in model_ids
    assert "gemini-2.5-flash" in model_ids
    assert "grok-beta" in model_ids

    # Each model exposes rates and labels for client UI
    first = models[0]
    assert "label" in first and "badge" in first and "description" in first
    assert "rate_summary" in first and "in /" in first["rate_summary"]

    # Test AgentView GET returns available_models
    res = client.get(f"/api/workspaces/{workspace.pk}/agent/")
    assert res.status_code == 200
    data = res.json()
    assert "available_models" in data
    assert len(data["available_models"]) >= 4

    # Test dedicated models endpoint
    res_models = client.get(f"/api/workspaces/{workspace.pk}/agent/models/")
    assert res_models.status_code == 200
    assert len(res_models.json()) >= 4


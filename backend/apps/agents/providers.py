"""Model providers behind one interface: `complete(messages, tools) -> Completion`.

The runtime speaks one message shape (OpenAI Responses items: role messages plus
`function_call` / `function_call_output` items, `developer` for instructions) and one
tool shape (`definitions()` in tools.py). Each adapter translates at the boundary, so
the agent graph, simple mode and segmentation never know which vendor answered.

Embeddings always go to OpenAI: stored vectors are 1536-dimension text-embedding-3
vectors, and switching the chat model must not invalidate the knowledge base.
"""

import hashlib
import json
import logging
import math
import re
from dataclasses import dataclass
from urllib.parse import quote

from django.conf import settings

from apps.channels.transport import ProviderError, RetryableError, request

PROVIDERS = ["openai", "anthropic", "gemini", "xai"]
PLATFORM_KEYS = {
    "openai": "PLATFORM_OPENAI_API_KEY",
    "anthropic": "PLATFORM_ANTHROPIC_API_KEY",
    "gemini": "PLATFORM_GEMINI_API_KEY",
    "xai": "PLATFORM_XAI_API_KEY",
}
MAX_OUTPUT_TOKENS = 1500


@dataclass
class Completion:
    text: str
    calls: list
    input_tokens: int
    output_tokens: int
    # The model that actually answered; differs from the configured one after a
    # fallback, and billing must charge what was used.
    model: str = ""


def platform_key(provider):
    key = getattr(settings, PLATFORM_KEYS[provider], "")
    if not key:
        raise ProviderError("platform_llm_key_missing")
    return key


def api_key_for(config, provider=None):
    """BYO workspaces use their own key; everyone else uses Instantlify's platform key for the
    provider and is debited from their prepaid balance."""
    provider = provider or config.provider
    if provider not in PLATFORM_KEYS:
        raise ProviderError("unsupported_llm_provider")
    if config.billing_mode == "byo_key":
        if provider != config.provider:
            # A BYO key belongs to one vendor; a fallback would silently spend ours.
            raise ProviderError("fallback_requires_platform_credits")
        if not config.api_key:
            raise ProviderError("llm_key_missing")
        return config.api_key
    return platform_key(provider)


def _enabled(workspace_id):
    from apps.platform_ops.security import assert_enabled

    assert_enabled(workspace_id, "ai")


def _split(messages):
    """(system text, conversation items). Instructions may appear anywhere in the list
    (the triage call puts them after the customer text); every vendor but OpenAI wants
    them separately."""
    system, items = [], []
    for item in messages:
        if isinstance(item, dict) and item.get("role") in {"developer", "system"}:
            system.append(str(item.get("content", "")))
        else:
            items.append(item)
    return "\n\n".join(part for part in system if part.strip()), items


def _arguments(raw):
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        value = {}
    return value if isinstance(value, dict) else {}


def _merge(out, role, part, key="content"):
    """Append a part, merging consecutive same-role turns (Anthropic and Gemini both
    expect a tool call and its result to sit in adjacent alternating turns)."""
    if out and out[-1]["role"] == role:
        out[-1][key].append(part)
    else:
        out.append({"role": role, key: [part]})


def _bookend(out, user_role, key, opener):
    """Conversations may open with our own outreach and must end on the customer."""
    if not out or out[0]["role"] != user_role:
        out.insert(0, {"role": user_role, key: [opener("(conversation start)")]})
    if out[-1]["role"] != user_role:
        out.append({"role": user_role, key: [opener("(continue)")]})
    return out


class OpenAIProvider:
    """OpenAI Responses API; also the only embedder."""

    def __init__(self, config, key=None, model=None):
        self.config = config
        self.model = model or config.model
        self.headers = {"Authorization": f"Bearer {key or api_key_for(config, 'openai')}"}

    def complete(self, messages, tools):
        _enabled(self.config.workspace_id)
        body = request(
            "POST",
            "https://api.openai.com/v1/responses",
            headers=self.headers,
            json={
                "model": self.model,
                "input": messages,
                "tools": tools,
                "store": False,
                "max_output_tokens": MAX_OUTPUT_TOKENS,
                "parallel_tool_calls": False,
            },
        )
        text = "".join(
            part.get("text", "")
            for item in body.get("output", [])
            if item.get("type") == "message"
            for part in item.get("content", [])
            if part.get("type") == "output_text"
        )
        calls = [
            {
                "name": item["name"],
                "arguments": item["arguments"],
                "call_id": item.get("call_id", ""),
            }
            for item in body.get("output", [])
            if item.get("type") == "function_call"
        ]
        usage = body.get("usage", {})
        return Completion(
            text,
            calls[:1],
            usage.get("input_tokens", 0),
            usage.get("output_tokens", 0),
            self.model,
        )

    def embed(self, texts):
        _enabled(self.config.workspace_id)
        body = request(
            "POST",
            "https://api.openai.com/v1/embeddings",
            headers=self.headers,
            json={"model": self.config.embedding_model, "input": texts, "dimensions": 1536},
        )
        vectors = [item["embedding"] for item in sorted(body["data"], key=lambda x: x["index"])]
        if len(vectors) != len(texts) or any(len(vector) != 1536 for vector in vectors):
            raise ProviderError("embedding_dimension_mismatch")
        return vectors, body.get("usage", {}).get("total_tokens", 0)


class AnthropicProvider:
    """Claude via the Messages API."""

    URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, config, key=None, model=None):
        self.config = config
        self.model = model or config.model
        self.headers = {
            "x-api-key": key or api_key_for(config, "anthropic"),
            "anthropic-version": "2023-06-01",
        }

    @staticmethod
    def convert(messages, tools):
        system, items = _split(messages)
        out = []
        for item in items:
            kind = item.get("type")
            if kind == "function_call":
                block = {
                    "type": "tool_use",
                    "id": item["call_id"],
                    "name": item["name"],
                    "input": _arguments(item["arguments"]),
                }
                _merge(out, "assistant", block)
            elif kind == "function_call_output":
                block = {
                    "type": "tool_result",
                    "tool_use_id": item["call_id"],
                    "content": str(item.get("output", "")),
                }
                _merge(out, "user", block)
            elif str(item.get("content", "")).strip():
                role = "user" if item.get("role") == "user" else "assistant"
                _merge(out, role, {"type": "text", "text": str(item["content"])})
        body = {
            "max_tokens": MAX_OUTPUT_TOKENS,
            "messages": _bookend(out, "user", "content", lambda t: {"type": "text", "text": t}),
        }
        if system:
            body["system"] = system
        if tools:
            body["tools"] = [
                {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "input_schema": tool["parameters"],
                }
                for tool in tools
            ]
        return body

    def complete(self, messages, tools):
        _enabled(self.config.workspace_id)
        body = request(
            "POST",
            self.URL,
            headers=self.headers,
            json={"model": self.model, **self.convert(messages, tools)},
        )
        blocks = body.get("content") or []
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        calls = [
            {"name": b["name"], "arguments": json.dumps(b.get("input") or {}), "call_id": b["id"]}
            for b in blocks
            if b.get("type") == "tool_use"
        ]
        usage = body.get("usage") or {}
        tokens_in = (
            usage.get("input_tokens", 0)
            + usage.get("cache_creation_input_tokens", 0)
            + usage.get("cache_read_input_tokens", 0)
        )
        return Completion(text, calls[:1], tokens_in, usage.get("output_tokens", 0), self.model)


class GeminiProvider:
    """Gemini via generateContent. Gemini's thinking models return a `thoughtSignature`
    on function calls that must be sent back with that call; it travels in the call ID,
    which the runtime already round-trips."""

    SIGNATURE = "sig:"

    def __init__(self, config, key=None, model=None):
        self.config = config
        self.model = model or config.model
        self.headers = {"x-goog-api-key": key or api_key_for(config, "gemini")}

    @staticmethod
    def _schema(value):
        # Gemini's function schema is an OpenAPI subset without these keywords.
        if isinstance(value, dict):
            return {
                k: GeminiProvider._schema(v)
                for k, v in value.items()
                if k not in {"additionalProperties", "strict", "$schema"}
            }
        return value

    @classmethod
    def convert(cls, messages, tools):
        system, items = _split(messages)
        out, names = [], {}
        for item in items:
            kind = item.get("type")
            if kind == "function_call":
                part = {
                    "functionCall": {"name": item["name"], "args": _arguments(item["arguments"])}
                }
                call_id = item.get("call_id", "")
                if call_id.startswith(cls.SIGNATURE):
                    part["thoughtSignature"] = call_id[len(cls.SIGNATURE) :]
                names[call_id] = item["name"]
                _merge(out, "model", part, "parts")
            elif kind == "function_call_output":
                try:
                    response = json.loads(item.get("output", ""))
                except ValueError:
                    response = item.get("output", "")
                if not isinstance(response, dict):
                    response = {"result": response}
                part = {
                    "functionResponse": {
                        "name": names.get(item.get("call_id", ""), ""),
                        "response": response,
                    }
                }
                _merge(out, "user", part, "parts")
            elif str(item.get("content", "")).strip():
                role = "user" if item.get("role") == "user" else "model"
                _merge(out, role, {"text": str(item["content"])}, "parts")
        body = {
            "contents": _bookend(out, "user", "parts", lambda t: {"text": t}),
            "generationConfig": {"maxOutputTokens": MAX_OUTPUT_TOKENS},
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if tools:
            body["tools"] = [
                {
                    "functionDeclarations": [
                        {
                            "name": tool["name"],
                            "description": tool.get("description", ""),
                            "parameters": cls._schema(tool["parameters"]),
                        }
                        for tool in tools
                    ]
                }
            ]
        return body

    def complete(self, messages, tools):
        _enabled(self.config.workspace_id)
        body = request(
            "POST",
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{quote(self.model, safe='')}:generateContent",
            headers=self.headers,
            json=self.convert(messages, tools),
        )
        candidates = body.get("candidates") or [{}]
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if "text" in p and not p.get("thought"))
        calls = []
        for index, part in enumerate(parts):
            if "functionCall" in part:
                signature = part.get("thoughtSignature")
                calls.append(
                    {
                        "name": part["functionCall"]["name"],
                        "arguments": json.dumps(part["functionCall"].get("args") or {}),
                        "call_id": self.SIGNATURE + signature if signature else f"call_{index}",
                    }
                )
        usage = body.get("usageMetadata") or {}
        return Completion(
            text,
            calls[:1],
            usage.get("promptTokenCount", 0),
            usage.get("candidatesTokenCount", 0) + usage.get("thoughtsTokenCount", 0),
            self.model,
        )


class XAIProvider:
    """Grok via xAI's OpenAI-compatible Chat Completions endpoint."""

    URL = "https://api.x.ai/v1/chat/completions"

    def __init__(self, config, key=None, model=None):
        self.config = config
        self.model = model or config.model
        self.headers = {"Authorization": f"Bearer {key or api_key_for(config, 'xai')}"}

    @staticmethod
    def convert(messages, tools):
        system, items = _split(messages)
        out = [{"role": "system", "content": system}] if system else []
        for item in items:
            kind = item.get("type")
            if kind == "function_call":
                call = {
                    "id": item["call_id"],
                    "type": "function",
                    "function": {"name": item["name"], "arguments": item["arguments"]},
                }
                if out and out[-1]["role"] == "assistant" and out[-1].get("tool_calls"):
                    out[-1]["tool_calls"].append(call)
                else:
                    out.append({"role": "assistant", "content": None, "tool_calls": [call]})
            elif kind == "function_call_output":
                out.append(
                    {
                        "role": "tool",
                        "tool_call_id": item["call_id"],
                        "content": str(item.get("output", "")),
                    }
                )
            elif str(item.get("content", "")).strip():
                role = "user" if item.get("role") == "user" else "assistant"
                out.append({"role": role, "content": str(item["content"])})
        body = {"messages": out, "max_tokens": MAX_OUTPUT_TOKENS}
        if tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool["parameters"],
                    },
                }
                for tool in tools
            ]
            body["parallel_tool_calls"] = False
        return body

    def complete(self, messages, tools):
        _enabled(self.config.workspace_id)
        body = request(
            "POST",
            self.URL,
            headers=self.headers,
            json={"model": self.model, **self.convert(messages, tools)},
        )
        message = ((body.get("choices") or [{}])[0]).get("message") or {}
        calls = [
            {
                "name": call["function"]["name"],
                "arguments": call["function"].get("arguments") or "{}",
                "call_id": call.get("id", ""),
            }
            for call in message.get("tool_calls") or []
        ]
        usage = body.get("usage") or {}
        return Completion(
            message.get("content") or "",
            calls[:1],
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
            self.model,
        )


ADAPTERS = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
    "xai": XAIProvider,
}


class FallbackProvider:
    """Try the primary; on a rate limit, overload or outage (RetryableError: 429, 5xx,
    connection failure) ask the secondary instead. Any other error is the request's
    fault and would fail the same way elsewhere, so it is raised."""

    def __init__(self, primary, secondary):
        self.primary, self.secondary = primary, secondary

    def complete(self, messages, tools):
        try:
            return self.primary.complete(messages, tools)
        except RetryableError:
            logging.getLogger(__name__).warning(
                "LLM provider unavailable; using fallback",
                extra={"event_code": "llm_fallback:" + type(self.secondary).__name__},
            )
            return self.secondary.complete(messages, tools)


# A fixed, valid comment-to-DM flow so local flow generation works without a model.
FAKE_FLOW = json.dumps(
    {
        "name": "[Local test] Comment to DM lead magnet",
        "start": "ask",
        "triggers": [{"kind": "comment", "keyword": "SEND", "channel": "instagram"}],
        "nodes": [
            {
                "id": "ask",
                "data": {
                    "kind": "send_message",
                    "text": "Thanks for commenting! What's the best email for your guide?",
                },
            },
            {"id": "email", "data": {"kind": "wait", "variable": "email"}},
            {
                "id": "guide",
                "data": {
                    "kind": "send_buttons",
                    "text": "Thanks! Here is your guide.",
                    "buttons": [
                        {"type": "web_url", "url": "https://example.com", "title": "Get the guide"}
                    ],
                },
            },
            {"id": "done", "data": {"kind": "end"}},
        ],
        "edges": [
            {"source": "ask", "target": "email"},
            {"source": "email", "target": "guide"},
            {"source": "guide", "target": "done"},
        ],
    }
)


class FakeLLMProvider:
    def complete(self, messages, tools):
        last = messages[-1] if messages else {}
        content = str(last.get("content", "")) if isinstance(last, dict) else ""
        if last.get("role") == "developer" and "Classify" in content:
            return Completion(
                '{"sentiment":"neutral","urgency":"normal","intent":"question"}', [], 5, 5
            )
        first = messages[0] if messages and isinstance(messages[0], dict) else {}
        instruction = str(first.get("content", ""))
        if instruction.startswith("CUSTOM_CONTACT_SEGMENTS:"):
            return Completion("[]", [], 5, 5)
        # Explicit test workspaces return unknown facts and a fixed false decision.
        if instruction.startswith("Extract only these fields as a JSON object: "):
            fields, _ = json.JSONDecoder().raw_decode(instruction.split(": ", 1)[1])
            return Completion(json.dumps(dict.fromkeys(fields)), [], 5, 5)
        if instruction.startswith("Evaluate the user condition. Return only"):
            return Completion('{"result":false}', [], 5, 5)
        if instruction.startswith("You are a business's chat assistant running one step"):
            # Local stand-in for the flow AI agent: finishes when the customer says bye.
            customer = [line for line in content.splitlines() if line.startswith("Customer:")]
            done = bool(customer) and "bye" in customer[-1].lower()
            reply = "" if done else "[Local test] Thanks! What else would you like to know?"
            return Completion(json.dumps({"reply": reply, "done": done}), [], 20, 10)
        if instruction.startswith("Decide which numbered intent"):
            # Local stand-in for intent matching: the first intent sharing a word of four
            # or more letters with the message, so test channels can exercise the path.
            words = {w for w in re.findall(r"[a-z]{4,}", content.lower())}
            options = re.findall(r"^(\d+)\. (.+)$", instruction, flags=re.MULTILINE)
            match = next(
                (
                    int(n)
                    for n, text in options
                    if words & set(re.findall(r"[a-z]{4,}", text.lower()))
                ),
                None,
            )
            return Completion(json.dumps({"match": match}), [], 5, 5)
        if str(first.get("content", "")).startswith("You are the Instantlify flow designer"):
            return Completion(FAKE_FLOW, [], 40, 120)
        return Completion(
            "[Local test] Thanks for reaching out. What would you like to know?", [], 20, 15
        )

    def embed(self, texts):
        vectors = []
        for text in texts:
            vector = [0.0] * 1536
            for word in text.lower().split():
                vector[int(hashlib.sha256(word.encode()).hexdigest()[:8], 16) % 1536] += 1
            length = math.sqrt(sum(x * x for x in vector)) or 1
            vectors.append([x / length for x in vector])
        return vectors, sum(len(text.split()) for text in texts)


def _test_provider():
    from apps.channels.adapters import test_channels_enabled

    if not test_channels_enabled():
        raise ProviderError("test_provider_disabled")
    return FakeLLMProvider()


def provider_for(config):
    _enabled(config.workspace_id)
    if config.is_test:
        return _test_provider()
    if config.provider not in ADAPTERS:
        raise ProviderError("unsupported_llm_provider")
    primary = ADAPTERS[config.provider](config)
    if config.fallback_provider and config.billing_mode == "platform_credits":
        if config.fallback_provider not in ADAPTERS:
            raise ProviderError("unsupported_llm_provider")
        key = platform_key(config.fallback_provider)
        secondary = ADAPTERS[config.fallback_provider](config, key, config.fallback_model)
        return FallbackProvider(primary, secondary)
    return primary


def embedder_for(config):
    """OpenAI for every chat provider. A BYO workspace on another vendor supplies an
    OpenAI key for its knowledge base; everyone else uses the platform key."""
    _enabled(config.workspace_id)
    if config.is_test:
        return _test_provider()
    if config.billing_mode == "byo_key":
        key = config.api_key if config.provider == "openai" else config.embedding_api_key
        if not key:
            raise ProviderError("embedding_key_missing")
        return OpenAIProvider(config, key)
    return OpenAIProvider(config, platform_key("openai"))

import hashlib
import math
from dataclasses import dataclass

from django.conf import settings

from apps.channels.transport import ProviderError, request


@dataclass
class Completion:
    text: str
    calls: list
    input_tokens: int
    output_tokens: int


class OpenAIProvider:
    def __init__(self, config):
        self.config = config
        if not config.api_key:
            raise ProviderError("llm_key_missing")
        self.headers = {"Authorization": f"Bearer {config.api_key}"}

    def complete(self, messages, tools):
        body = request(
            "POST",
            "https://api.openai.com/v1/responses",
            headers=self.headers,
            json={
                "model": self.config.model,
                "input": messages,
                "tools": tools,
                "store": False,
                "max_output_tokens": 1500,
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
            text, calls[:1], usage.get("input_tokens", 0), usage.get("output_tokens", 0)
        )

    def embed(self, texts):
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


class FakeLLMProvider:
    def complete(self, messages, tools):
        last = messages[-1] if messages else {}
        content = str(last.get("content", "")) if isinstance(last, dict) else ""
        if last.get("role") == "developer" and "Classify" in content:
            return Completion(
                '{"sentiment":"neutral","urgency":"normal","intent":"question"}', [], 5, 5
            )
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


def provider_for(config):
    if config.is_test:
        if settings.CHANNEL_ADAPTER_MODE != "fake":
            raise ProviderError("test_provider_disabled")
        return FakeLLMProvider()
    if config.provider != "openai":
        raise ProviderError("unsupported_llm_provider")
    return OpenAIProvider(config)

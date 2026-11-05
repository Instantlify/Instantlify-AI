"""Platform-side LLM calls — segment classification and Nemio's own support agent.

These run on Nemio's platform key and are never billed to a tenant's credit balance,
because they are our work, not theirs. They are also deliberately separate from
`apps.agents`: that runtime is scoped to a workspace and grounded in a tenant's
knowledge base, and the two must never retrieve into each other's context.

With `CHANNEL_ADAPTER_MODE == "fake"` every call is served deterministically offline,
so the test suite never needs a live key.
"""

import hashlib
import json
import math
import os
import re
import time

from django.conf import settings

from apps.channels.transport import ProviderError, request

EMBEDDING_DIMENSIONS = 1536


def platform_key():
    key = settings.PLATFORM_OPENAI_API_KEY
    if not key:
        raise ProviderError("platform_llm_key_missing")
    return key


def fake_mode():
    return settings.CHANNEL_ADAPTER_MODE == "fake"


def _fake_vector(text):
    vector = [0.0] * EMBEDDING_DIMENSIONS
    for word in text.lower().split():
        vector[int(hashlib.sha256(word.encode()).hexdigest()[:8], 16) % EMBEDDING_DIMENSIONS] += 1
    length = math.sqrt(sum(value * value for value in vector)) or 1
    return [value / length for value in vector]


def embed(texts):
    """Returns (vectors, tokens). Used for the platform knowledge base only."""
    texts = list(texts)
    if not texts:
        return [], 0
    if fake_mode():
        return [_fake_vector(text) for text in texts], sum(len(t.split()) for t in texts)
    body = request(
        "POST",
        "https://api.openai.com/v1/embeddings",
        headers={"Authorization": f"Bearer {platform_key()}"},
        json={"model": "text-embedding-3-small", "input": texts},
    )
    vectors = [item["embedding"] for item in body.get("data", [])]
    return vectors, body.get("usage", {}).get("total_tokens", 0)


def complete(system, user, *, max_tokens=500):
    if fake_mode():
        return _fake_completion(system, user)
    body = request(
        "POST",
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {platform_key()}"},
        json={
            "model": settings.PLATFORM_AI_MODEL,
            "input": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "store": False,
            "max_output_tokens": max_tokens,
        },
    )
    return "".join(
        part.get("text", "")
        for item in body.get("output", [])
        if item.get("type") == "message"
        for part in item.get("content", [])
        if part.get("type") == "output_text"
    )


def _fake_completion(system, user):
    """Deterministic stand-in. For classification it keyword-matches against the
    candidate list so tests assert real behaviour rather than a fixed string."""
    if "classify" in system.lower():
        options = [
            line.strip("- ").strip() for line in system.splitlines() if line.startswith("- ")
        ]
        haystack = user.lower()
        for option in options:
            head = option.split("/")[0].split("(")[0].strip().lower()
            if head and head in haystack:
                return json.dumps({"category": option, "confidence": 0.9, "evidence": head})
        return json.dumps({"category": "", "confidence": 0.0, "evidence": "no signal"})
    return "Thanks for reaching out — a teammate will follow up shortly."


def classify_account(*, handle, display_name, bio, site_text, categories):
    """Assign one marketing category to a connected account, or none at all.

    Returning nothing is a real answer: a thin bio genuinely does not say what a
    business does, and a forced guess pollutes every segment count downstream.
    """
    if not categories:
        return None
    system = (
        "You classify a social account into exactly one marketing category.\n"
        'Reply with JSON: {"category": str, "confidence": 0-1, "evidence": str}.\n'
        "Use an empty category when the evidence is too thin to be confident.\n"
        "Candidates:\n" + "\n".join(f"- {name}" for name in categories)
    )
    user = (
        f"handle: @{handle}\ndisplay name: {display_name}\nbio: {bio}\n"
        f"linked site: {site_text[:1500]}"
    )
    try:
        raw = complete(system, user, max_tokens=200)
        parsed = json.loads(raw)
    except (ProviderError, json.JSONDecodeError, TypeError):
        return None
    category = str(parsed.get("category", "")).strip()
    if category not in categories:
        return None
    try:
        confidence = float(parsed.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence < 0.5:
        return None
    return {
        "category": category,
        "confidence": round(min(1.0, confidence), 2),
        "evidence": str(parsed.get("evidence", ""))[:500],
    }


def retrieve_sections(question, *, limit=6):
    """Top-k platform knowledge sections for the support agent. Reads only
    `PlatformKnowledgeSection` — a tenant's documents are a different table and
    cannot be reached from here."""
    from pgvector.django import CosineDistance

    from .models import PlatformKnowledgeSection

    sections = PlatformKnowledgeSection.objects.filter(embedding__isnull=False)
    if not sections.exists():
        return []
    vectors, _ = embed([question])
    if not vectors:
        return []
    return list(
        sections.select_related("document")
        .annotate(distance=CosineDistance("embedding", vectors[0]))
        .order_by("distance")[:limit]
    )


# ------------------------------------------------------------ provider key health
# One card per platform key found in the environment. `PLATFORM_ANTHROPIC_API_KEY_MARKO`
# becomes "Anthropic (Marko)", so several named keys per provider can be rotated and
# tested independently. Nothing here runs on a schedule: a test spends a real request.

PROVIDER_LABELS = {
    "OPENAI": "OpenAI",
    "ANTHROPIC": "Anthropic",
    "GEMINI": "Gemini",
    "XAI": "Grok (xAI)",
}
KEY_PATTERN = re.compile(r"^PLATFORM_(OPENAI|ANTHROPIC|GEMINI|XAI)_API_KEY(?:_([A-Z0-9]+))?$")


def provider_keys(environ=None):
    """Every platform provider key configured, plus an unconfigured placeholder for
    each provider that has none, so a missing key is visible rather than silent."""
    environ = os.environ if environ is None else environ
    found = {}
    for name, value in environ.items():
        match = KEY_PATTERN.match(name)
        if match and value:
            found[name] = (match.group(1), match.group(2))
    if settings.PLATFORM_OPENAI_API_KEY:
        found.setdefault("PLATFORM_OPENAI_API_KEY", ("OPENAI", None))
    keys = []
    for name, (provider, label) in sorted(found.items()):
        title = PROVIDER_LABELS[provider] + (f" ({label.title()})" if label else "")
        keys.append({"env": name, "provider": provider.lower(), "label": title, "configured": True})
    present = {key["provider"] for key in keys}
    for provider, title in PROVIDER_LABELS.items():
        if provider.lower() not in present:
            keys.append(
                {
                    "env": f"PLATFORM_{provider}_API_KEY",
                    "provider": provider.lower(),
                    "label": title,
                    "configured": False,
                }
            )
    return keys


def _key_value(env):
    if env == "PLATFORM_OPENAI_API_KEY" and settings.PLATFORM_OPENAI_API_KEY:
        return settings.PLATFORM_OPENAI_API_KEY
    return os.environ.get(env, "")


def ping(env):
    """One minimal paid call against a single key. Returns {"ok", "ms", "error"}.

    The error is a short code, never the provider's response body, which can echo
    request details back."""
    match = KEY_PATTERN.match(env)
    if not match:
        raise ValueError("Unknown provider key.")
    key = _key_value(env)
    if not key:
        return {"ok": False, "ms": None, "error": "not_configured"}
    if fake_mode():
        return {"ok": True, "ms": 0, "error": ""}
    provider = match.group(1)
    calls = {
        "OPENAI": (
            "https://api.openai.com/v1/responses",
            {"Authorization": f"Bearer {key}"},
            {"model": settings.PLATFORM_AI_MODEL, "input": "ok", "max_output_tokens": 16, "store": False},
        ),
        "ANTHROPIC": (
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": key, "anthropic-version": "2023-06-01"},
            {
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "ok"}],
            },
        ),
        "GEMINI": (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{settings.PLATFORM_GEMINI_MODEL}:generateContent",
            {"x-goog-api-key": key},
            {
                "contents": [{"parts": [{"text": "ok"}]}],
                "generationConfig": {"maxOutputTokens": 1},
            },
        ),
        "XAI": (
            "https://api.x.ai/v1/chat/completions",
            {"Authorization": f"Bearer {key}"},
            {
                "model": "grok-3-mini",
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "ok"}],
            },
        ),
    }
    url, headers, body = calls[provider]
    started = time.monotonic()
    try:
        request("POST", url, headers=headers, json=body)
    except ProviderError as exc:
        return {"ok": False, "ms": round((time.monotonic() - started) * 1000), "error": exc.code}
    return {"ok": True, "ms": round((time.monotonic() - started) * 1000), "error": ""}

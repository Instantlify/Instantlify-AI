"""Curated platform models and live rate card resolution for client workspaces."""

from decimal import Decimal

from django.conf import settings

from apps.billing.credits import resolve_rate
from apps.billing.models import ModelPricingRate

PLATFORM_MODELS = [
    {
        "id": "gpt-5.4-mini",
        "provider": "openai",
        "label": "GPT-5.4 Mini",
        "badge": "Recommended · Fast",
        "description": "Fast, smart, and cost-effective. Best for high-volume sales qualification, customer support, and instant lead capture.",
    },
    {
        "id": "claude-sonnet-5",
        "provider": "anthropic",
        "label": "Claude Sonnet 5",
        "badge": "High Intelligence",
        "description": "Deep conversational nuance, human-like empathy, and multi-step reasoning. Best for consultative sales and complex deals.",
    },
    {
        "id": "gemini-2.5-flash",
        "provider": "gemini",
        "label": "Gemini 2.5 Flash",
        "badge": "Ultra Fast",
        "description": "Sub-second response speed with high throughput. Keeps inbound prospects instantly engaged without lag.",
    },
    {
        "id": "grok-beta",
        "provider": "xai",
        "label": "xAI Grok",
        "badge": "Direct & Punchy",
        "description": "Punchy, modern conversational style. Well suited for creator brands, direct response, and dynamic social DMs.",
    },
]


def format_rate(cents):
    amount = Decimal(cents) / Decimal(100)
    text = format(amount, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    whole, _, fraction = text.partition(".")
    return f"${whole}.{fraction.ljust(2, '0')}"


def rate_provider(model):
    if model.startswith(("gpt-", "o1", "o3", "o4")):
        return "openai"
    if model.startswith("claude-"):
        return "anthropic"
    if model.startswith("gemini-"):
        return "gemini"
    if model.startswith("grok-"):
        return "xai"
    return None


def get_platform_models():
    """Returns curated models with live rates matched against the platform rate card."""
    results = []
    entries = list(PLATFORM_MODELS)
    for provider, model in [
        ("openai", settings.PLATFORM_AI_MODEL),
        ("gemini", settings.PLATFORM_GEMINI_MODEL),
    ]:
        if not any(entry["id"] == model for entry in entries):
            entries.append(
                {
                    "id": model,
                    "provider": provider,
                    "label": model,
                    "badge": "Platform configured",
                    "description": "The model configured for this provider on your Instantlify server.",
                }
            )
    # Exact admin entries can add supported chat models to the catalogue. Wildcard
    # entries price known models but cannot identify a model to send to a provider.
    for rate in ModelPricingRate.objects.filter(is_fallback_default=False).order_by(
        "model_pattern"
    ):
        model = rate.model_pattern
        provider = rate_provider(model)
        if "%" not in model and provider and not any(entry["id"] == model for entry in entries):
            entries.append(
                {
                    "id": model,
                    "provider": provider,
                    "label": rate.label or model,
                    "badge": "Admin configured",
                    "description": "Configured in the Instantlify admin rate card.",
                }
            )
    for entry in entries:
        # Display the same rate resolver used by the real credit debit, including fallbacks.
        rate = resolve_rate(entry["id"])
        our_input = rate.our_input
        our_output = rate.our_output

        input_dollars = format_rate(our_input)
        output_dollars = format_rate(our_output)

        results.append(
            {
                "id": entry["id"],
                "provider": entry["provider"],
                "label": entry["label"],
                "badge": entry["badge"],
                "description": entry["description"],
                "input_rate": input_dollars,
                "output_rate": output_dollars,
                "rate_summary": f"{input_dollars} in / {output_dollars} out per 1M tokens",
                "rate_source": "fallback" if rate.is_fallback_default else "model",
                "rate_pattern": rate.model_pattern,
                "rate_label": rate.label or rate.model_pattern,
            }
        )
    return results

"""Curated platform models and live rate card resolution for client workspaces."""

from decimal import Decimal
from apps.billing.models import ModelPricingRate

PLATFORM_MODELS = [
    {
        "id": "gpt-5.4-mini",
        "provider": "openai",
        "label": "GPT-5.4 Mini",
        "badge": "Recommended · Fast",
        "description": "Fast, smart, and cost-effective. Best for high-volume sales qualification, customer support, and instant lead capture.",
        "default_our_input": Decimal("60.00"),   # cents / 1M ($0.60)
        "default_our_output": Decimal("240.00"), # cents / 1M ($2.40)
    },
    {
        "id": "claude-sonnet-5",
        "provider": "anthropic",
        "label": "Claude Sonnet 5",
        "badge": "High Intelligence",
        "description": "Deep conversational nuance, human-like empathy, and multi-step reasoning. Best for consultative sales and complex deals.",
        "default_our_input": Decimal("300.00"),  # $3.00
        "default_our_output": Decimal("1500.00"),# $15.00
    },
    {
        "id": "gemini-2.5-flash",
        "provider": "gemini",
        "label": "Gemini 2.5 Flash",
        "badge": "Ultra Fast",
        "description": "Sub-second response speed with high throughput. Keeps inbound prospects instantly engaged without lag.",
        "default_our_input": Decimal("30.00"),   # $0.30
        "default_our_output": Decimal("120.00"), # $1.20
    },
    {
        "id": "grok-beta",
        "provider": "xai",
        "label": "xAI Grok",
        "badge": "Direct & Punchy",
        "description": "Punchy, modern conversational style. Well suited for creator brands, direct response, and dynamic social DMs.",
        "default_our_input": Decimal("80.00"),   # $0.80
        "default_our_output": Decimal("320.00"), # $3.20
    },
]


def get_platform_models():
    """Returns curated models with live rates matched against the platform rate card."""
    results = []
    for entry in PLATFORM_MODELS:
        rate = ModelPricingRate.objects.filter(model_pattern=entry["id"]).first()
        if not rate:
            # Fallback search by provider prefix or fallback rate
            rate = (
                ModelPricingRate.objects.filter(is_fallback_default=False)
                .filter(model_pattern__startswith=entry["id"].split("-")[0])
                .first()
            )
        our_input = rate.our_input if rate else entry["default_our_input"]
        our_output = rate.our_output if rate else entry["default_our_output"]

        input_dollars = f"${(Decimal(our_input) / Decimal(100)):.2f}"
        output_dollars = f"${(Decimal(our_output) / Decimal(100)):.2f}"

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
            }
        )
    return results

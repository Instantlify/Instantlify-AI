from unittest.mock import patch

import httpx
import pytest

from apps.channels.transport import ProviderError, _request
from apps.platform_ops.templatetags.credit_money import credit_money


@pytest.mark.parametrize(
    "value,expected",
    [
        ("0.00039", "0.00039"),
        ("-0.00039", "-0.00039"),
        ("26.99961", "26.99961"),
        ("27", "27.00"),
        ("0", "0.00"),
        ("0.000001", "0.000001"),
    ],
)
def test_credit_amounts_preserve_stored_precision(value, expected):
    assert credit_money(value) == expected


def test_invalid_google_key_has_a_specific_safe_error():
    response = httpx.Response(
        400, json={"error": {"code": 400, "details": [{"reason": "API_KEY_INVALID"}]}}
    )
    with patch("httpx.request", return_value=response):
        with pytest.raises(ProviderError, match="invalid_api_key"):
            _request(
                "POST",
                "https://generativelanguage.googleapis.com/v1beta/models/test:generateContent",
            )


@pytest.mark.django_db
def test_configured_model_is_selectable_at_the_actual_fallback_rate(settings):
    from apps.agents.catalog import get_platform_models
    from apps.billing.models import ModelPricingRate

    settings.PLATFORM_AI_MODEL = "openai-configured-test-model"
    ModelPricingRate.objects.filter(is_fallback_default=True).update(our_input=123, our_output=456)
    model = next(row for row in get_platform_models() if row["id"] == settings.PLATFORM_AI_MODEL)
    assert model["input_rate"] == "$1.23"
    assert model["output_rate"] == "$4.56"

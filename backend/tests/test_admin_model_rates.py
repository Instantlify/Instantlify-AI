from decimal import Decimal

import pytest

from apps.agents.catalog import format_rate, get_platform_models
from apps.billing.models import ModelPricingRate

pytestmark = pytest.mark.django_db


def test_model_rate_uses_admin_values_and_updates_without_code_changes(client, workspace):
    rate = ModelPricingRate.objects.create(
        model_pattern="gemini-2.5%",
        label="Gemini selling price",
        our_input=Decimal("123.4567"),
        our_output=Decimal("1000"),
        real_input=1,
        real_output=2,
    )

    def card():
        response = client.get(f"/api/workspaces/{workspace.pk}/agent/")
        assert response.status_code == 200
        return next(
            item for item in response.json()["available_models"] if item["id"] == "gemini-2.5-flash"
        )

    row = card()
    assert row["input_rate"] == "$1.234567"
    assert row["output_rate"] == "$10.00"
    assert row["rate_source"] == "model"
    assert row["rate_label"] == rate.label and row["rate_pattern"] == rate.model_pattern
    rate.our_input = Decimal("17.5")
    rate.save()
    assert card()["input_rate"] == "$0.175"


def test_admin_exact_models_are_included_and_specific_rates_win():
    ModelPricingRate.objects.create(model_pattern="claude-%", our_input=100, our_output=200)
    ModelPricingRate.objects.create(
        model_pattern="claude-admin-test",
        label="My configured Claude",
        our_input=321,
        our_output=654,
    )
    ModelPricingRate.objects.create(model_pattern="text-embedding-custom", our_input=1)
    rows = get_platform_models()
    card = next(row for row in rows if row["id"] == "claude-admin-test")
    assert card["input_rate"] == "$3.21" and card["output_rate"] == "$6.54"
    assert card["label"] == "My configured Claude"
    assert card["rate_pattern"] == "claude-admin-test"
    assert not any(row["id"] in ["claude-%", "text-embedding-custom"] for row in rows)


def test_admin_fallback_is_identified_not_disguised_as_specific_price():
    ModelPricingRate.objects.filter(is_fallback_default=True).update(our_input=789, our_output=1234)
    row = next(item for item in get_platform_models() if item["id"] == "grok-beta")
    assert row["input_rate"] == "$7.89" and row["output_rate"] == "$12.34"
    assert row["rate_source"] == "fallback"


@pytest.mark.parametrize(
    "cents,expected", [(0, "$0.00"), (1000, "$10.00"), (2000, "$20.00"), ("0.0001", "$0.000001")]
)
def test_rate_format_preserves_admin_precision(cents, expected):
    assert format_rate(cents) == expected

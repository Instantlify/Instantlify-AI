from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import stripe
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.billing.models import PlanPrice

pytestmark = pytest.mark.django_db


class FakeStripe:
    """Records calls and answers retrieves from what has been created so far."""

    def __init__(self, products=None, prices=None):
        self.products_store = dict(products or {})
        self.prices_store = dict(prices or {})
        self.created_prices = []
        self.created_products = []
        self.updated_products = []

        self.products = MagicMock()
        self.products.retrieve.side_effect = self._retrieve_product
        self.products.create.side_effect = self._create_product
        self.products.update.side_effect = self._update_product
        self.prices = MagicMock()
        self.prices.retrieve.side_effect = self._retrieve_price
        self.prices.create.side_effect = self._create_price

    def _retrieve_product(self, product_id):
        if product_id not in self.products_store:
            raise stripe.InvalidRequestError("No such product", "id")
        return SimpleNamespace(id=product_id, name=self.products_store[product_id]["name"])

    def _update_product(self, product_id, params):
        self.updated_products.append((product_id, params))
        self.products_store[product_id].update(params)

    def _create_product(self, params):
        self.created_products.append(params)
        self.products_store[params["id"]] = params
        return SimpleNamespace(id=params["id"])

    def _retrieve_price(self, price_id):
        if price_id not in self.prices_store:
            raise stripe.InvalidRequestError("No such price", "id")
        return SimpleNamespace(id=price_id, unit_amount=self.prices_store[price_id])

    def _create_price(self, params):
        self.created_prices.append(params)
        # Count the whole store, not this run, so a second run cannot mint an id that
        # collides with one the first run already handed out.
        price_id = f"price_{len(self.prices_store) + 1}"
        self.prices_store[price_id] = params["unit_amount"]
        return SimpleNamespace(id=price_id, unit_amount=params["unit_amount"])


def run(fake, settings, **options):
    settings.STRIPE_SECRET_KEY = options.pop("key", "sk_test_abc")
    out = StringIO()
    with patch("stripe.StripeClient", return_value=fake):
        call_command("publish_plans", stdout=out, **options)
    return out.getvalue()


def test_publishes_every_priced_interval_and_stores_the_ids(settings):
    fake = FakeStripe()
    run(fake, settings)

    published = PlanPrice.objects.exclude(stripe_price_id="")
    assert published.count() == len(fake.created_prices)
    assert published.count() == PlanPrice.objects.filter(price_cents__gt=0).count()
    # Stripe's own interval names, not Instantlify's.
    intervals = {call["recurring"]["interval"] for call in fake.created_prices}
    assert intervals == {"month", "year"}
    assert {p["id"] for p in fake.created_products} == {"nemio-starter", "nemio-pro", "nemio-scale"}


def test_free_and_custom_tiers_are_not_published(settings):
    fake = FakeStripe()
    run(fake, settings)
    slugs = {call["metadata"]["nemio_plan"] for call in fake.created_prices}
    assert "free" not in slugs and "dev" not in slugs


def test_rerunning_creates_nothing_further(settings):
    first = FakeStripe()
    run(first, settings)
    again = FakeStripe(products=first.products_store, prices=first.prices_store)
    output = run(again, settings)
    assert again.created_prices == []
    assert again.created_products == []
    assert "0 price(s) published" in output


def test_a_changed_amount_is_reported_rather_than_guessed(settings):
    fake = FakeStripe()
    run(fake, settings)
    price = PlanPrice.objects.exclude(stripe_price_id="").first()
    original = price.stripe_price_id
    PlanPrice.objects.filter(pk=price.pk).update(price_cents=price.price_cents + 700)

    rerun = FakeStripe(products=fake.products_store, prices=fake.prices_store)
    output = run(rerun, settings)
    assert "mismatch" in output
    assert rerun.created_prices == []
    price.refresh_from_db()
    assert price.stripe_price_id == original, "existing subscribers must keep their price"


def test_replace_issues_a_new_price_for_a_changed_amount(settings):
    fake = FakeStripe()
    run(fake, settings)
    price = PlanPrice.objects.exclude(stripe_price_id="").first()
    original = price.stripe_price_id
    PlanPrice.objects.filter(pk=price.pk).update(price_cents=price.price_cents + 700)

    rerun = FakeStripe(products=fake.products_store, prices=fake.prices_store)
    run(rerun, settings, replace=True)
    price.refresh_from_db()
    assert price.stripe_price_id != original
    assert len(rerun.created_prices) == 1


def test_dry_run_calls_nothing_and_stores_nothing(settings):
    fake = FakeStripe()
    output = run(fake, settings, dry_run=True)
    assert fake.created_prices == [] and fake.created_products == []
    assert not PlanPrice.objects.exclude(stripe_price_id="").exists()
    assert "would create" in output


def test_a_live_key_needs_the_live_flag(settings):
    fake = FakeStripe()
    with pytest.raises(CommandError, match="live key"):
        run(fake, settings, key="sk_live_realmoney")
    assert fake.created_prices == []


def test_a_price_missing_from_this_account_is_reported_not_recreated(settings):
    """Pointing at a different Stripe account must not silently mint duplicates."""
    price = PlanPrice.objects.filter(price_cents__gt=0).first()
    PlanPrice.objects.filter(pk=price.pk).update(stripe_price_id="price_from_another_account")
    fake = FakeStripe()
    output = run(fake, settings)
    price.refresh_from_db()
    assert price.stripe_price_id == "price_from_another_account"
    assert "not in this Stripe account" in output


def test_missing_key_is_refused(settings):
    with pytest.raises(CommandError, match="STRIPE_SECRET_KEY"):
        run(FakeStripe(), settings, key="")


def test_existing_product_is_rebranded_without_changing_prices(settings):
    fake = FakeStripe()
    run(fake, settings)
    original_ids = list(PlanPrice.objects.values_list("id", "stripe_price_id", "price_cents"))
    fake.products_store["nemio-pro"]["name"] = "Nemio Pro"
    again = FakeStripe(products=fake.products_store, prices=fake.prices_store)
    run(again, settings)
    assert again.updated_products == [("nemio-pro", {"name": "Instantlify Pro"})]
    assert again.created_products == again.created_prices == []
    assert (
        list(PlanPrice.objects.values_list("id", "stripe_price_id", "price_cents")) == original_ids
    )


def test_dry_run_does_not_rename_existing_products(settings):
    fake = FakeStripe(products={"nemio-pro": {"name": "Nemio Pro"}})
    output = run(fake, settings, dry_run=True)
    assert "would rename product nemio-pro to Instantlify Pro" in output
    assert fake.updated_products == []

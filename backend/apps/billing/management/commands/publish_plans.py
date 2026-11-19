"""Create the Stripe products and prices for the tiers in the database.

Plans, intervals and amounts live in `billing.Plan` / `PlanPrice`; Stripe only needs to
be told about them once. This writes each created price back onto its `PlanPrice`, which
is the same field the console's tier form edits, so publishing and hand-entering IDs
cannot disagree.

Idempotent: products use a deterministic `instantlify-<slug>` id, and a `PlanPrice` that
already carries an id is verified rather than recreated. Re-running after adding a tier
publishes only the new one.

A Stripe price is immutable. When an amount changes, the old price keeps billing existing
subscribers until they move, so this reports the mismatch and refuses to guess; issue the
new price deliberately with --replace.

    python manage.py publish_plans --dry-run
    python manage.py publish_plans
    python manage.py publish_plans --replace   # new price for changed amounts
"""

import stripe
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.billing.models import Plan, PlanPrice

STRIPE_INTERVAL = {"monthly": "month", "annual": "year"}


class Command(BaseCommand):
    help = "Create Stripe products and prices for the active plans in the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Report what would change; call nothing."
        )
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Issue a new price where the amount no longer matches Stripe.",
        )
        parser.add_argument(
            "--live",
            action="store_true",
            help="Required to run against a live key, which bills real customers.",
        )
        parser.add_argument("--currency", default="usd")

    def handle(self, *args, **options):
        key = settings.STRIPE_SECRET_KEY
        if not key:
            raise CommandError("STRIPE_SECRET_KEY is not set.")
        if key.startswith("sk_live_") and not options["live"]:
            raise CommandError(
                "That is a live key. Re-run with --live once you mean to publish tiers "
                "that will bill real customers."
            )
        self.client = stripe.StripeClient(key)
        self.dry_run = options["dry_run"]
        mode = "test" if key.startswith("sk_test_") else "LIVE"
        self.stdout.write(f"Stripe mode: {mode}{'  (dry run)' if self.dry_run else ''}")

        published = skipped = mismatched = 0
        # Custom tiers are partner deals priced by hand, and a tier with no price rows is
        # free; neither belongs in Stripe.
        plans = Plan.objects.filter(is_active=True, is_custom=False).order_by("sort_order", "slug")
        for plan in plans:
            prices = plan.prices.filter(price_cents__gt=0).order_by("billing_interval")
            if not prices:
                continue
            product_id = self.ensure_product(plan)
            for price in prices:
                result = self.ensure_price(plan, price, product_id, options)
                published += result == "published"
                skipped += result == "skipped"
                mismatched += result == "mismatch"

        self.stdout.write(
            self.style.SUCCESS(
                f"\n{published} price(s) published, {skipped} already current, "
                f"{mismatched} amount mismatch(es)."
            )
        )
        if mismatched:
            self.stdout.write(
                "A mismatch means the database amount and the Stripe price disagree. "
                "Re-run with --replace to issue a new price; existing subscribers stay "
                "on the old one until they change plan."
            )
        if published and not self.dry_run:
            self.stdout.write(
                "Metered overage prices are not created here: they need a Stripe Meter "
                f"named {settings.STRIPE_METER_EVENT_NAME!r}. Add those in the console."
            )

    def ensure_product(self, plan):
        product_id = f"instantlify-{plan.slug}"
        try:
            product = self.client.products.retrieve(product_id)
            expected_name = f"Instantlify {plan.name}"
            if product.name != expected_name:
                if self.dry_run:
                    self.stdout.write(f"  would rename product {product_id} to {expected_name}")
                else:
                    self.client.products.update(product_id, {"name": expected_name})
                    self.stdout.write(f"  renamed product {product_id} to {expected_name}")
            else:
                self.stdout.write(f"  product {product_id} current")
        except stripe.InvalidRequestError:
            if self.dry_run:
                self.stdout.write(f"  would create product {product_id} ({plan.name})")
            else:
                # A fixed id is what makes re-running safe without searching by metadata.
                self.client.products.create(
                    {
                        "id": product_id,
                        "name": f"Instantlify {plan.name}",
                        "metadata": {"instantlify_plan": plan.slug},
                    }
                )
                self.stdout.write(self.style.SUCCESS(f"  created product {product_id}"))
        return product_id

    def ensure_price(self, plan, price, product_id, options):
        label = f"{plan.slug}/{price.billing_interval}"
        if price.stripe_price_id:
            try:
                existing = self.client.prices.retrieve(price.stripe_price_id)
            except stripe.InvalidRequestError:
                self.stdout.write(
                    self.style.WARNING(
                        f"  {label}: {price.stripe_price_id} is not in this Stripe account. "
                        "Clear the field in the console, or switch to the account that has it."
                    )
                )
                return "mismatch"
            if existing.unit_amount == price.price_cents:
                self.stdout.write(f"  {label}: {price.stripe_price_id} current")
                return "skipped"
            self.stdout.write(
                self.style.WARNING(
                    f"  {label}: database has {price.price_cents}, Stripe price has "
                    f"{existing.unit_amount}"
                )
            )
            if not options["replace"]:
                return "mismatch"

        if self.dry_run:
            self.stdout.write(f"  would create {label} at {price.price_cents} cents")
            return "published"
        created = self.client.prices.create(
            {
                "product": product_id,
                "currency": options["currency"],
                "unit_amount": price.price_cents,
                "recurring": {"interval": STRIPE_INTERVAL[price.billing_interval]},
                "metadata": {"instantlify_plan": plan.slug, "instantlify_interval": price.billing_interval},
            }
        )
        PlanPrice.objects.filter(pk=price.pk).update(stripe_price_id=created.id)
        self.stdout.write(self.style.SUCCESS(f"  {label}: created {created.id}"))
        return "published"

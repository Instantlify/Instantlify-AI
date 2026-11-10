"""Verify real Stripe test events through the running local webhook listener."""

import json
import logging
import time
import uuid
from urllib.parse import urlsplit

import stripe
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.billing.models import BillingAccount, BillingEvent, PlanPrice
from apps.billing.stripe_data import stripe_data
from apps.tenants.models import Workspace


class Command(BaseCommand):
    help = "Verify signed Stripe test callbacks using a new isolated trial subscription."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Create test fixtures after verifying that the key is in test mode.",
        )

    def handle(self, *args, **options):
        if not options["apply"]:
            self.stdout.write(
                "Start tools/stripe_local.py, recreate the backend environment, then run with --apply."
            )
            return
        key = settings.STRIPE_SECRET_KEY
        if not key or not key.startswith(("sk_test_", "rk_test_")):
            raise CommandError("This command requires a Stripe test key.")
        if urlsplit(settings.PUBLIC_APP_URL).hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise CommandError("This verification command is limited to a local application.")
        logging.getLogger("stripe").setLevel(logging.WARNING)
        self.key = key
        try:
            if stripe.Balance.retrieve(api_key=key).livemode:
                raise CommandError("Refusing to create fixtures in a live Stripe account.")
            price = (
                PlanPrice.objects.filter(plan__is_active=True, billing_interval="monthly")
                .exclude(stripe_price_id="")
                .order_by("plan__sort_order")
                .first()
            )
            if not price:
                raise CommandError("Publish a monthly Stripe test price first.")
            provider_price = stripe.Price.retrieve(price.stripe_price_id, api_key=key)
            if provider_price.livemode or not provider_price.active or not provider_price.recurring:
                raise CommandError("The selected plan must have an active recurring test price.")
            self.verify(price)
        except CommandError:
            raise
        except Exception as error:
            raise CommandError(
                f"Local Stripe verification failed ({type(error).__name__}). No provider response or secret was printed."
            ) from None

    def report(self, **data):
        self.stdout.write(json.dumps(data))
        self.stdout.flush()

    def wait_for(
        self, workspace_id, subscription_id, expected_status, *, minimum_events=1, price_id=None
    ):
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            account = BillingAccount.objects.for_workspace(workspace_id).get()
            events = BillingEvent.objects.for_workspace(workspace_id)
            if (
                account.subscription_id == subscription_id
                and account.status == expected_status
                and (price_id is None or account.plan_price_id == price_id)
                and events.filter(status="processed").count() >= minimum_events
            ):
                return account, events.count()
            if events.filter(status="failed").exists():
                raise CommandError("A signed billing event arrived but could not be reconciled.")
            time.sleep(1)
        raise CommandError(
            "No reconciled callback arrived within 90 seconds. Check the local listener and signing secret."
        )

    def verify(self, price):
        marker = uuid.uuid4().hex
        # No memberships or email recipients: this fixture cannot notify an existing user.
        workspace = Workspace.objects.create(name=f"Stripe local verification {marker[:8]}")
        customer = stripe.Customer.create(
            name="Instantlify local webhook verification",
            metadata={"nemio_local_verification": marker},
            api_key=self.key,
            idempotency_key=f"nemio-local-customer:{marker}",
        )
        BillingAccount.objects.for_workspace(workspace).create(
            workspace=workspace, customer_id=customer.id
        )
        self.report(
            stage="fixture_ready",
            mode="test",
            workspace_id=str(workspace.pk),
            customer_id=customer.id,
        )
        subscription = None
        try:
            subscription = stripe.Subscription.create(
                customer=customer.id,
                items=[{"price": price.stripe_price_id}],
                trial_period_days=7,
                trial_settings={"end_behavior": {"missing_payment_method": "cancel"}},
                metadata={"nemio_local_verification": marker},
                api_key=self.key,
                idempotency_key=f"nemio-local-subscription:{marker}",
            )
            account, count = self.wait_for(workspace.pk, subscription.id, "trialing")
            if account.plan_price_id != price.pk or account.period_end is None:
                raise CommandError(
                    "The callback did not map the test price and billing period correctly."
                )
            self.report(
                stage="created_callback_verified",
                status=account.status,
                plan=account.plan,
                events=count,
            )
            before = (
                BillingEvent.objects.for_workspace(workspace).filter(status="processed").count()
            )
            stripe.Subscription.modify(
                subscription.id,
                metadata={"nemio_local_verification": marker, "verification_stage": "updated"},
                api_key=self.key,
                idempotency_key=f"nemio-local-update:{marker}",
            )
            account, count = self.wait_for(
                workspace.pk, subscription.id, "trialing", minimum_events=before + 1
            )
            self.report(stage="updated_callback_verified", status=account.status, events=count)
            alternate = (
                PlanPrice.objects.filter(plan__is_active=True, billing_interval="monthly")
                .exclude(stripe_price_id="")
                .exclude(plan_id=price.plan_id)
                .order_by("plan__sort_order")
                .first()
            )
            if alternate:
                provider_price = stripe.Price.retrieve(alternate.stripe_price_id, api_key=self.key)
                if (
                    provider_price.livemode
                    or not provider_price.active
                    or not provider_price.recurring
                ):
                    raise CommandError(
                        "The alternate plan must have an active recurring test price."
                    )
                # Both switches stay inside the trial and explicitly disable proration.
                for stage, target in [("plan_changed", alternate), ("plan_restored", price)]:
                    current = stripe_data(
                        stripe.Subscription.retrieve(subscription.id, api_key=self.key)
                    )
                    if current["status"] != "trialing" or current["customer"] != customer.id:
                        raise CommandError("Refusing a test plan switch outside its owned trial.")
                    before = (
                        BillingEvent.objects.for_workspace(workspace)
                        .filter(status="processed")
                        .count()
                    )
                    stripe.Subscription.modify(
                        subscription.id,
                        items=[
                            {
                                "id": current["items"]["data"][0]["id"],
                                "price": target.stripe_price_id,
                            }
                        ],
                        proration_behavior="none",
                        api_key=self.key,
                        idempotency_key=f"nemio-local-{stage}:{marker}",
                    )
                    account, count = self.wait_for(
                        workspace.pk,
                        subscription.id,
                        "trialing",
                        minimum_events=before + 1,
                        price_id=target.pk,
                    )
                    self.report(
                        stage=f"{stage}_callback_verified",
                        status=account.status,
                        plan=account.plan,
                        events=count,
                    )
            else:
                self.report(stage="plan_switch_skipped", reason="no_alternate_test_plan")
        finally:
            if subscription:
                # Only the subscription created above, verified again before cancellation.
                current = stripe.Subscription.retrieve(subscription.id, api_key=self.key)
                if (
                    current.livemode
                    or stripe_data(current).get("metadata", {}).get("nemio_local_verification")
                    != marker
                ):
                    raise CommandError(
                        "Test-fixture ownership could not be confirmed; no cancellation was attempted."
                    )
                stripe.Subscription.cancel(
                    subscription.id,
                    api_key=self.key,
                    idempotency_key=f"nemio-local-cancel:{marker}",
                )
                account, count = self.wait_for(workspace.pk, subscription.id, "canceled")
                self.report(
                    stage="cancellation_callback_verified", status=account.status, events=count
                )
        self.report(
            result="passed",
            mode="test",
            real_charges=False,
            existing_workspaces_changed=False,
            workspace_id=str(workspace.pk),
            subscription_id=subscription.id,
        )

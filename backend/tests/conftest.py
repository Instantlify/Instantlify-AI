import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.tenants.models import User
from apps.tenants.services import create_workspace


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="owner", email="owner@example.com", password="A-very-long-password42"
    )


@pytest.fixture
def workspace(user):
    return create_workspace(user, "Acme")


@pytest.fixture
def client(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


DEFAULT_TEST_LIMITS = {
    "max_instagram_accounts": 1,
    "max_contacts": None,
    "team_seats": 1,
    "max_ai_messages": 100,
    "ai_agent_enabled": True,
    "integrations_unlocked": True,
    "content_scheduling_enabled": True,
    "voice_notes_enabled": True,
}


def set_limits(workspace, **changes):
    """Move the workspace onto a private custom plan with these limits."""
    import uuid

    from apps.billing.models import Plan, PlanLimits, PlanPrice
    from apps.billing.services import account_for

    plan = Plan.objects.create(slug=f"test-{uuid.uuid4().hex[:8]}", name="Test", is_custom=True)
    PlanLimits.objects.create(plan=plan, **{**DEFAULT_TEST_LIMITS, **changes})
    price = PlanPrice.objects.create(plan=plan, billing_interval="monthly", price_cents=0)
    account = account_for(workspace.pk)
    account.plan_price = price
    account.save()
    return plan


def price_for(slug, interval="monthly", stripe_price_id=None):
    from apps.billing.models import PlanPrice

    price = PlanPrice.objects.get(plan__slug=slug, billing_interval=interval)
    if stripe_price_id is not None:
        price.stripe_price_id = stripe_price_id
        price.save(update_fields=["stripe_price_id"])
    return price

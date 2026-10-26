from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.tenants.models import Workspace

pytestmark = pytest.mark.django_db


def test_local_stripe_verification_is_read_only_without_apply():
    with patch("stripe.Balance.retrieve") as balance, patch("stripe.Customer.create") as create:
        call_command("verify_stripe_local", stdout=StringIO())
    balance.assert_not_called()
    create.assert_not_called()


def test_local_stripe_verification_refuses_live_accounts(settings):
    settings.STRIPE_SECRET_KEY = "sk_test_example"
    settings.PUBLIC_APP_URL = "http://localhost:3000"
    before = Workspace.objects.count()
    with patch("stripe.Balance.retrieve") as balance, patch("stripe.Customer.create") as create:
        balance.return_value.livemode = True
        with pytest.raises(CommandError, match="live Stripe"):
            call_command("verify_stripe_local", apply=True, stdout=StringIO())
    create.assert_not_called()
    assert Workspace.objects.count() == before


def test_local_stripe_verification_refuses_nonlocal_app(settings):
    settings.STRIPE_SECRET_KEY = "sk_test_example"
    settings.PUBLIC_APP_URL = "https://example.com"
    with (
        patch("stripe.Customer.create") as create,
        pytest.raises(CommandError, match="local application"),
    ):
        call_command("verify_stripe_local", apply=True, stdout=StringIO())
    create.assert_not_called()

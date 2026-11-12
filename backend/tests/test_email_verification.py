import re
from datetime import timedelta

import pytest
from django.conf import settings
from django.core import mail
from django.utils import timezone
from rest_framework.test import APIClient

from apps.billing.credits import balance_for
from apps.billing.models import AICreditTransaction
from apps.tenants.models import User, Workspace
from apps.tenants.services import create_workspace
from apps.tenants.tasks import purge_unverified_signups
from apps.tenants.verification import make_token

pytestmark = pytest.mark.django_db

SIGNUP = {"name": "Sam", "email": "sam@example.com", "password": "Saffron!River42Cloud"}


def signup(client=None):
    client = client or APIClient()
    response = client.post("/api/auth/signup/", SIGNUP)
    assert response.status_code == 201
    return client, response


def token_from_email():
    """The welcome mail for a new workspace lands in the same outbox, so pick the
    message that actually carries a confirmation link."""
    links = [re.search(r"#token=(\S+)", m.body) for m in mail.outbox]
    found = [match.group(1) for match in links if match]
    assert len(found) == 1, f"expected one confirmation link, found {len(found)}"
    return found[0]


def test_signup_sends_a_confirmation_link_and_reports_unverified():
    client, response = signup()
    assert response.json()["email_verified"] is False
    assert client.get("/api/auth/me/").status_code == 403
    assert len(mail.outbox) == 1
    assert SIGNUP["email"] in mail.outbox[0].to


def test_confirming_marks_the_account_and_grants_the_welcome_credit():
    client, _ = signup()
    workspace = create_workspace(User.objects.get(email=SIGNUP["email"]), "Acme")
    assert balance_for(workspace.pk).balance_cents == 0

    response = APIClient().post("/api/auth/verify-email/", {"token": token_from_email()})
    assert response.status_code == 200
    assert client.get("/api/auth/me/").status_code == 403
    assert (
        client.post(
            "/api/auth/login/", {"email": SIGNUP["email"], "password": SIGNUP["password"]}
        ).status_code
        == 200
    )
    assert client.get("/api/auth/me/").json()["email_verified"] is True
    assert balance_for(workspace.pk).balance_cents == settings.SIGNUP_CREDIT_CENTS


def test_the_welcome_credit_is_granted_once_however_often_the_link_is_used():
    signup()
    workspace = create_workspace(User.objects.get(email=SIGNUP["email"]), "Acme")
    token = token_from_email()
    for _ in range(3):
        assert APIClient().post("/api/auth/verify-email/", {"token": token}).status_code == 200
    assert balance_for(workspace.pk).balance_cents == settings.SIGNUP_CREDIT_CENTS
    assert AICreditTransaction.all_objects.filter(type="adjustment").count() == 1


def test_an_agency_client_workspace_gets_no_grant_of_its_own(user):
    """Child balances resolve to the agency parent, so granting per client workspace
    would pay the same agency again for every workspace it creates."""
    agency = create_workspace(user, "Agency")
    client_workspace = Workspace.objects.create(name="Client", parent=agency)
    from apps.tenants.models import Membership

    Membership.objects.for_workspace(client_workspace).create(
        workspace=client_workspace, user=user, role=Membership.Role.OWNER
    )
    user.email_verified_at = None
    user.save(update_fields=["email_verified_at"])
    APIClient().post("/api/auth/verify-email/", {"token": make_token(user)})
    assert balance_for(agency.pk).balance_cents == settings.SIGNUP_CREDIT_CENTS


def test_a_link_stops_working_once_the_address_changes():
    signup()
    token = token_from_email()
    user = User.objects.get(email=SIGNUP["email"])
    user.email = "someone.else@example.com"
    user.save(update_fields=["email"])
    response = APIClient().post("/api/auth/verify-email/", {"token": token})
    assert response.status_code == 400
    user.refresh_from_db()
    assert user.email_verified_at is None


def test_a_tampered_link_is_refused():
    signup()
    token = token_from_email()
    assert APIClient().post("/api/auth/verify-email/", {"token": token[:-3]}).status_code == 400


def test_resend_says_the_same_thing_for_a_stranger_as_for_an_account():
    signup()
    mail.outbox.clear()
    known = APIClient().post("/api/auth/verify-email/resend/", {"email": SIGNUP["email"]})
    unknown = APIClient().post("/api/auth/verify-email/resend/", {"email": "nobody@example.com"})
    assert known.json() == unknown.json()
    assert len(mail.outbox) == 1


def test_purge_releases_an_abandoned_address_but_keeps_real_accounts(user):
    """An unconfirmed signup holds a unique address against whoever actually owns it."""
    stale = User.objects.create_user(
        username="stale", email="stale@example.com", password="Saffron!River42Cloud"
    )
    with_workspace = User.objects.create_user(
        username="joined", email="joined@example.com", password="Saffron!River42Cloud"
    )
    create_workspace(with_workspace, "Acme")
    confirmed = User.objects.create_user(
        username="confirmed", email="confirmed@example.com", password="Saffron!River42Cloud"
    )
    confirmed.email_verified_at = timezone.now()
    confirmed.save(update_fields=["email_verified_at"])

    old = timezone.now() - timedelta(days=settings.UNVERIFIED_SIGNUP_DAYS + 1)
    User.objects.update(date_joined=old)

    purge_unverified_signups()
    assert not User.objects.filter(pk=stale.pk).exists()
    assert User.objects.filter(pk=with_workspace.pk).exists()
    assert User.objects.filter(pk=confirmed.pk).exists()


def test_purge_leaves_a_recent_signup_alone():
    signup()
    purge_unverified_signups()
    assert User.objects.filter(email=SIGNUP["email"]).exists()

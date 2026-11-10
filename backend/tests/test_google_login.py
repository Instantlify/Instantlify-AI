from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest
from rest_framework.test import APIClient

from apps.tenants.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def google(settings):
    settings.GOOGLE_CLIENT_ID = "cid"
    settings.GOOGLE_CLIENT_SECRET = "secret"
    settings.PUBLIC_APP_URL = "https://app.example.com"


def start(client):
    res = client.get("/api/auth/google/start/")
    assert res.status_code == 302
    query = parse_qs(urlsplit(res["Location"]).query)
    assert query["redirect_uri"] == ["https://app.example.com/api/auth/google/callback/"]
    return query["state"][0]


def callback(client, state, profile):
    with patch(
        "apps.tenants.google_login.http_request",
        side_effect=[{"access_token": "at"}, profile],
    ):
        return client.get("/api/auth/google/callback/", {"state": state, "code": "c"})


def test_new_google_user_is_created_verified_and_signed_in(google):
    client = APIClient()
    assert client.get("/api/auth/google/").json() == {"enabled": True}
    state = start(client)
    res = callback(
        client, state, {"email": "New@Example.com", "email_verified": True, "name": "New Person"}
    )
    assert res["Location"] == "https://app.example.com/auth/"
    user = User.objects.get(email="new@example.com")
    assert user.email_verified_at is not None and not user.has_usable_password()
    assert client.get("/api/auth/me/").status_code == 200


def test_existing_account_signs_in_and_state_is_single_use(google, user):
    client = APIClient()
    state = start(client)
    res = callback(client, state, {"email": "owner@example.com", "email_verified": True})
    assert res["Location"] == "https://app.example.com/auth/"
    assert User.objects.filter(email__iexact="owner@example.com").count() == 1
    replay = callback(APIClient(), state, {"email": "owner@example.com", "email_verified": True})
    assert "google_error=invalid_state" in replay["Location"]


def test_unverified_email_and_banned_accounts_are_refused(google, user):
    client = APIClient()
    res = callback(client, start(client), {"email": "x@example.com", "email_verified": False})
    assert "email_not_verified" in res["Location"]
    user.is_banned = True
    user.save()
    res = callback(client, start(client), {"email": "owner@example.com", "email_verified": True})
    assert "account_unavailable" in res["Location"]


def test_disabled_without_credentials(settings):
    settings.GOOGLE_CLIENT_ID = ""
    client = APIClient()
    assert client.get("/api/auth/google/").json() == {"enabled": False}
    assert "not_configured" in client.get("/api/auth/google/start/")["Location"]

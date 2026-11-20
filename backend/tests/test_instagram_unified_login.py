"""Unified Login exchange: locating the granted Instagram account from the token."""

from unittest.mock import patch

import pytest

from apps.channels.instagram import unified_exchange
from apps.channels.transport import ProviderError


def fake_meta(debug, assigned=None):
    calls = []

    def respond(method, url, **kwargs):
        calls.append((method, url))
        if url.endswith("/oauth/access_token"):
            return {"access_token": "suat"}
        if url.endswith("/debug_token"):
            return {"data": {"is_valid": True, "app_id": "123", **debug}}
        if url.endswith("/me/assigned_instagram_accounts"):
            return {"data": assigned or []}
        if url.endswith("/subscribed_apps"):
            return {"success": True}
        return {"username": "shop", "name": "Shop"}

    return respond, calls


@pytest.fixture(autouse=True)
def meta_app(settings):
    settings.META_APP_ID = "123"
    settings.META_APP_SECRET = "secret"


def test_uses_granular_scope_targets_when_present():
    respond, calls = fake_meta(
        {"granular_scopes": [{"scope": "instagram_manage_messages", "target_ids": ["17841"]}]}
    )
    with patch("apps.channels.instagram.request", side_effect=respond):
        credentials = unified_exchange("code")
    assert credentials.account_id == "17841"
    assert not any(url.endswith("assigned_instagram_accounts") for _, url in calls)


@pytest.mark.parametrize(
    "debug",
    [
        {"granular_scopes": [{"scope": "instagram_manage_messages"}]},
        {"scopes": ["instagram_manage_messages"], "granular_scopes": []},
    ],
)
def test_falls_back_to_assigned_accounts_without_targets(debug):
    respond, _ = fake_meta(debug, assigned=[{"id": "17841", "username": "shop"}])
    with patch("apps.channels.instagram.request", side_effect=respond):
        credentials = unified_exchange("code")
    assert credentials.account_id == "17841"
    assert credentials.display_name == "shop"


@pytest.mark.parametrize(
    ("assigned", "error"),
    [
        ([], "instagram_messaging_grant_has_no_targets"),
        ([{"id": "1"}, {"id": "2"}], "instagram_messaging_grant_has_multiple_targets"),
    ],
)
def test_assigned_accounts_must_resolve_to_one(assigned, error):
    respond, _ = fake_meta({"scopes": ["instagram_manage_messages"]}, assigned=assigned)
    with (
        patch("apps.channels.instagram.request", side_effect=respond),
        pytest.raises(ProviderError) as raised,
    ):
        unified_exchange("code")
    assert raised.value.code == error


def test_missing_messaging_permission_is_reported():
    respond, _ = fake_meta({"scopes": ["instagram_basic"]})
    with (
        patch("apps.channels.instagram.request", side_effect=respond),
        pytest.raises(ProviderError) as raised,
    ):
        unified_exchange("code")
    assert raised.value.code == "instagram_messaging_grant_missing"

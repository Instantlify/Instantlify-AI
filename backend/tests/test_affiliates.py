from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.channels.transport import AmbiguousDelivery
from apps.platform_ops.affiliates import customer_id, public_data
from apps.platform_ops.models import AffiliateAccount

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def affiliate_settings(user):
    user.email_verified_at = timezone.now()
    user.save(update_fields=["email_verified_at"])
    with override_settings(
        FIRSTPROMOTER_API_KEY="test-secret", FIRSTPROMOTER_ACCOUNT_ID="test-account"
    ):
        yield


def promoter(user):
    return {
        "id": 42,
        "cust_id": customer_id(user),
        "email": user.email,
        "stats": {"clicks_count": 7, "revenue_amount": 1234},
        "promoter_campaigns": [
            {"campaign": {"name": "Partners"}, "ref_link": "https://example.com/?ref=abc"}
        ],
    }


def test_unconfigured_and_unverified_never_contact_provider(client, user):
    with patch("apps.platform_ops.affiliates.provider_request") as provider:
        with override_settings(FIRSTPROMOTER_API_KEY=""):
            assert client.get("/api/affiliate/").json()["status"] == "unavailable"
            assert client.post("/api/affiliate/").status_code == 503
        user.email_verified_at = None
        user.save(update_fields=["email_verified_at"])
        assert client.get("/api/affiliate/").json()["status"] == "verify_email"
        assert client.post("/api/affiliate/").status_code == 403
        provider.assert_not_called()


def test_read_does_not_enroll_and_enrollment_is_idempotent(client, user):
    data = promoter(user)
    with patch(
        "apps.platform_ops.affiliates.provider_request", return_value={"data": []}
    ) as provider:
        assert client.get("/api/affiliate/").json()["status"] == "not_enrolled"
        assert not AffiliateAccount.objects.exists()
        assert all(call.args[0] == "GET" for call in provider.call_args_list)
    with patch(
        "apps.platform_ops.affiliates.provider_request", side_effect=[{"data": []}, data]
    ) as provider:
        response = client.post("/api/affiliate/", {}, format="json")
        assert response.status_code == 201, response.content
        assert response.json()["revenue"] == "12.34"
        assert "test-secret" not in response.content.decode()
        payload = provider.call_args.kwargs["json"]
        assert payload["cust_id"] == customer_id(user) and payload["drip_emails"] is False
        assert provider.call_args.kwargs["side_effect"] is True
    with patch(
        "apps.platform_ops.affiliates.provider_request", return_value={"data": [data]}
    ) as provider:
        assert client.post("/api/affiliate/", {}, format="json").status_code == 200
        assert provider.call_count == 1 and provider.call_args.args[0] == "GET"


def test_same_email_without_owner_binding_cannot_be_claimed(client, user):
    foreign = {**promoter(user), "cust_id": "another-account"}
    with patch("apps.platform_ops.affiliates.provider_request", return_value={"data": [foreign]}):
        assert client.get("/api/affiliate/").status_code == 503
        assert client.post("/api/affiliate/", {}, format="json").status_code == 503
    assert not AffiliateAccount.objects.filter(promoter_id=42).exists()


def test_uncertain_enrollment_does_not_duplicate_and_refresh_reconciles(client, user):
    with patch(
        "apps.platform_ops.affiliates.provider_request",
        side_effect=[{"data": []}, AmbiguousDelivery()],
    ):
        assert client.post("/api/affiliate/", {}, format="json").status_code == 503
    assert AffiliateAccount.objects.get(user=user).status == "needs_review"
    with patch(
        "apps.platform_ops.affiliates.provider_request", return_value={"data": []}
    ) as provider:
        assert client.post("/api/affiliate/", {}, format="json").status_code == 409
        assert provider.call_count == 1
    with patch(
        "apps.platform_ops.affiliates.provider_request", return_value={"data": [promoter(user)]}
    ):
        assert client.get("/api/affiliate/").json()["status"] == "active"
    assert AffiliateAccount.objects.get(user=user).promoter_id == 42


def test_stored_account_is_checked_and_provider_links_are_sanitized(client, user):
    AffiliateAccount.objects.create(user=user, promoter_id=42, status="active")
    with patch(
        "apps.platform_ops.affiliates.provider_request",
        return_value={**promoter(user), "cust_id": "foreign"},
    ):
        assert client.get("/api/affiliate/").status_code == 503
    data = public_data(
        {
            "stats": {"clicks_count": -1, "revenue_amount": "NaN"},
            "promoter_campaigns": [
                {"ref_link": "javascript:alert(1)"},
                {"ref_link": "https://user:pass@example.com"},
            ],
        }
    )
    assert data["stats"]["clicks_count"] == 0 and data["revenue"] is None
    assert all(not row["ref_link"] for row in data["campaigns"])

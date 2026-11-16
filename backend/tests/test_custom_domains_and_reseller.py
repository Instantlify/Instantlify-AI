"""Phase 5 tests: Custom domain verification, On-Demand TLS authorization,
dynamic host routing, and agency reseller consolidated billing.
"""

import pytest
from rest_framework.exceptions import PermissionDenied

from apps.agents.models import AgentConfig
from apps.billing import credits
from apps.billing.credits import balance_for
from apps.billing.gating import limits_for
from apps.billing.reseller import (
    effective_billing_workspace_id,
    is_reseller_client,
)
from apps.billing.services import account_for, reserve_usage
from apps.tenants.domain_verification import (
    verify_custom_domain,
)
from apps.tenants.models import WorkspaceBranding
from apps.tenants.services import create_workspace
from tests.conftest import set_limits

pytestmark = pytest.mark.django_db


# ---------------- Custom Domain Lifecycle & Verification ----------------


def test_branding_domain_lifecycle(client, workspace):
    url = f"/api/workspaces/{workspace.pk}/branding/"

    # 1. Initially empty
    res = client.get(url)
    assert res.status_code == 200
    assert res.data["effective"]["custom_domain"] == ""
    assert res.data["effective"]["custom_domain_status"] == "pending"

    # 2. Set custom domain
    res = client.put(
        url,
        {
            "brand_name": "Agency Brand",
            "custom_domain": "app.agency.com",
            "primary_color": "#123456",
        },
        format="json",
    )
    assert res.status_code == 200
    data = res.data
    assert data["custom_domain"] == "app.agency.com"
    assert data["custom_domain_status"] == "pending"
    assert len(data["verification_token"]) == 48
    assert data["tls_status"] == "inactive"
    assert data["verified_at"] is None

    first_token = data["verification_token"]

    # 3. Change domain -> token rotates, stays pending
    res = client.put(
        url,
        {
            "brand_name": "Agency Brand",
            "custom_domain": "portal.agency.com",
            "primary_color": "#123456",
        },
        format="json",
    )
    assert res.status_code == 200
    assert res.data["custom_domain"] == "portal.agency.com"
    assert res.data["verification_token"] != first_token
    assert res.data["custom_domain_status"] == "pending"

    # 4. Clear domain -> status reset, token cleared
    res = client.put(
        url,
        {"brand_name": "Agency Brand", "custom_domain": ""},
        format="json",
    )
    assert res.status_code == 200
    assert res.data["custom_domain"] == ""
    assert res.data["verification_token"] == ""


def test_verify_custom_domain_txt_challenge(workspace):
    branding = WorkspaceBranding.objects.for_workspace(workspace).create(
        workspace=workspace,
        brand_name="Agency",
        custom_domain="app.myclient.com",
        verification_token="token-abc-123",
        custom_domain_status=WorkspaceBranding.DomainStatus.PENDING,
    )

    def mock_resolver(domain, record_type):
        if domain == "_instantlify-challenge.app.myclient.com" and record_type == "TXT":
            return ["instantlify-verify=token-abc-123"]
        return []

    verified, msg = verify_custom_domain(branding, resolver=mock_resolver)
    assert verified is True
    branding.refresh_from_db()
    assert branding.custom_domain_status == WorkspaceBranding.DomainStatus.ACTIVE
    assert branding.tls_status == WorkspaceBranding.TLSStatus.ACTIVE
    assert branding.verified_at is not None


def test_verify_custom_domain_cname(workspace):
    branding = WorkspaceBranding.objects.for_workspace(workspace).create(
        workspace=workspace,
        brand_name="Agency",
        custom_domain="app.customcname.com",
        verification_token="token-xyz",
        custom_domain_status=WorkspaceBranding.DomainStatus.PENDING,
    )

    def mock_resolver(domain, record_type):
        if domain == "app.customcname.com" and record_type == "CNAME":
            return ["domains.instantlify.com."]
        return []

    verified, msg = verify_custom_domain(branding, resolver=mock_resolver)
    assert verified is True
    branding.refresh_from_db()
    assert branding.custom_domain_status == WorkspaceBranding.DomainStatus.ACTIVE
    assert branding.tls_status == WorkspaceBranding.TLSStatus.ACTIVE


def test_verify_custom_domain_failure(workspace):
    branding = WorkspaceBranding.objects.for_workspace(workspace).create(
        workspace=workspace,
        brand_name="Agency",
        custom_domain="app.unconfigured.com",
        verification_token="token-fail",
        custom_domain_status=WorkspaceBranding.DomainStatus.PENDING,
    )

    def mock_resolver(domain, record_type):
        return []

    verified, msg = verify_custom_domain(branding, resolver=mock_resolver)
    assert verified is False
    assert "Verification failed" in msg
    branding.refresh_from_db()
    assert branding.custom_domain_status == WorkspaceBranding.DomainStatus.FAILED
    assert branding.tls_status == WorkspaceBranding.TLSStatus.ERROR


def test_verify_domain_api_endpoint(client, workspace):
    WorkspaceBranding.objects.for_workspace(workspace).create(
        workspace=workspace,
        brand_name="Agency",
        custom_domain="portal.verified.com",
        verification_token="test-token-789",
        custom_domain_status=WorkspaceBranding.DomainStatus.PENDING,
    )

    verify_url = f"/api/workspaces/{workspace.pk}/branding/verify-domain/"

    # Without DNS records -> fails with 400
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "apps.tenants.domain_verification.query_dns_records",
            lambda d, r: [],
        )
        res = client.post(verify_url)
        assert res.status_code == 400
        assert res.data["verified"] is False
        assert res.data["branding"]["custom_domain_status"] == "failed"

    # With correct TXT record -> succeeds with 200
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "apps.tenants.domain_verification.query_dns_records",
            lambda d, r: ["instantlify-verify=test-token-789"] if r == "TXT" else [],
        )
        res = client.post(verify_url)
        assert res.status_code == 200
        assert res.data["verified"] is True
        assert res.data["branding"]["custom_domain_status"] == "active"


# ---------------- Caddy On-Demand TLS & Dynamic Allowed Hosts ----------------


def test_caddy_tls_ask_endpoint(client, workspace):
    tls_url = "/api/v1/tls/check-domain/"

    # Missing domain parameter -> 400
    res = client.get(tls_url)
    assert res.status_code == 400
    assert res.data["allowed"] is False

    # Platform domains always allowed -> 200
    for host in ["localhost", "127.0.0.1", "app.instantlify.com", "ops.instantlify.com"]:
        res = client.get(f"{tls_url}?domain={host}")
        assert res.status_code == 200
        assert res.data["allowed"] is True

    # Unknown domain -> 404
    res = client.get(f"{tls_url}?domain=rogue.attacker.com")
    assert res.status_code == 404
    assert res.data["allowed"] is False

    # Pending domain -> 404
    WorkspaceBranding.objects.for_workspace(workspace).create(
        workspace=workspace,
        brand_name="Agency",
        custom_domain="pending.agency.com",
        custom_domain_status=WorkspaceBranding.DomainStatus.PENDING,
    )
    res = client.get(f"{tls_url}?domain=pending.agency.com")
    assert res.status_code == 404
    assert res.data["allowed"] is False

    # Active verified domain -> 200
    WorkspaceBranding.all_objects.filter(custom_domain="pending.agency.com").update(
        custom_domain_status=WorkspaceBranding.DomainStatus.ACTIVE
    )
    res = client.get(f"{tls_url}?domain=pending.agency.com")
    assert res.status_code == 200
    assert res.data["allowed"] is True


def test_dynamic_allowed_hosts(workspace, settings):
    from config.settings.base import DynamicAllowedHosts

    settings.ALLOWED_HOSTS = DynamicAllowedHosts(settings.ALLOWED_HOSTS)

    # Base host in ALLOWED_HOSTS
    assert "localhost" in settings.ALLOWED_HOSTS

    # Non-existent domain not in ALLOWED_HOSTS
    assert "notregistered.agency.com" not in settings.ALLOWED_HOSTS

    # Add active custom domain
    WorkspaceBranding.objects.for_workspace(workspace).create(
        workspace=workspace,
        brand_name="Agency",
        custom_domain="live.clientbrand.com",
        custom_domain_status=WorkspaceBranding.DomainStatus.ACTIVE,
    )

    # DynamicAllowedHosts detects it
    assert "live.clientbrand.com" in settings.ALLOWED_HOSTS
    assert "LIVE.CLIENTBRAND.COM" in settings.ALLOWED_HOSTS


# ---------------- Reseller (Agency) Consolidated Billing ----------------


def test_reseller_billing_account_and_limits_rollup(user, workspace):
    # workspace is the parent Agency
    set_limits(workspace, team_seats=15, max_ai_messages=500)
    agency_account = account_for(workspace.pk)
    agency_account.status = "active"
    agency_account.save()

    # Create managed client workspace
    client_ws = create_workspace(user, "Client Store")
    client_ws.parent = workspace
    client_ws.save()

    assert is_reseller_client(client_ws.pk) is True
    assert is_reseller_client(workspace.pk) is False
    assert effective_billing_workspace_id(client_ws.pk) == workspace.pk

    # Client account_for() resolves to Agency BillingAccount
    resolved_account = account_for(client_ws.pk)
    assert resolved_account.pk == agency_account.pk

    # Client limits_for() resolves to Agency PlanLimits
    limits = limits_for(client_ws.pk)
    assert limits.team_seats == 15
    assert limits.max_ai_messages == 500


def test_reseller_credit_balance_rollup(user, workspace):
    # Agency starts with credits
    credits.credit(workspace.pk, key="seed:10000", amount_cents=10000, type="adjustment")
    assert balance_for(workspace.pk).balance_cents == 10000

    # Create managed client workspace
    client_ws = create_workspace(user, "Client Store")
    client_ws.parent = workspace
    client_ws.save()

    # Client balance_for() shares the Agency's credit balance
    client_balance = balance_for(client_ws.pk)
    agency_balance = balance_for(workspace.pk)
    assert client_balance.pk == agency_balance.pk
    assert client_balance.balance_cents == 10000


def test_reseller_billing_pause_cascades_to_client(user, workspace):
    set_limits(workspace)
    agency_account = account_for(workspace.pk)
    agency_account.status = "canceled"
    agency_account.save()

    client_ws = create_workspace(user, "Client Store")
    client_ws.parent = workspace
    client_ws.save()

    cfg = AgentConfig.objects.for_workspace(client_ws.pk).create(
        workspace=client_ws,
        billing_mode="platform_credits",
    )

    with pytest.raises(PermissionDenied, match="AI is paused until billing is active"):
        reserve_usage(cfg, key="turn-1")

import pytest

from apps.platform_ops.models import EmailTemplate
from apps.tenants.branding import DEFAULT_BRANDING
from apps.tenants.domain_verification import verify_custom_domain
from apps.tenants.models import WorkspaceBranding


@pytest.mark.django_db
def test_seeded_templates_and_default_branding_use_instantlify():
    for row in EmailTemplate.objects.filter(name__in=["welcome-v2", "workspace-invitation"]):
        assert "Instantlify" in row.subject + row.body
    assert DEFAULT_BRANDING["brand_name"] == "Instantlify"


@pytest.mark.django_db
def test_instantlify_dns_record_verifies(workspace):
    branding = WorkspaceBranding.objects.for_workspace(workspace).create(
        workspace=workspace,
        brand_name="Agency",
        custom_domain="portal.example.com",
        verification_token="test-token",
    )

    def resolver(host, kind):
        return (
            ["instantlify-verify=test-token"]
            if host == "_instantlify-challenge.portal.example.com" and kind == "TXT"
            else []
        )

    assert verify_custom_domain(branding, resolver=resolver)[0]

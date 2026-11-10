import importlib
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.db import connection

from apps.platform_ops.models import EmailTemplate
from apps.tenants.branding import DEFAULT_BRANDING
from apps.tenants.domain_verification import verify_custom_domain
from apps.tenants.models import WorkspaceBranding


@pytest.mark.django_db
def test_rebrand_updates_untouched_templates_and_preserves_custom_copy():
    migration = importlib.import_module("apps.platform_ops.migrations.0013_instantlify_brand")
    seeds = importlib.import_module("apps.platform_ops.migrations.0006_seed_growth_content")
    _name, _description, subject, body, _status = seeds.TEMPLATES[0]
    row = EmailTemplate.objects.get(name="welcome-v2")
    row.subject, row.body = subject, body
    row.save()
    invitation = EmailTemplate.objects.get(name="workspace-invitation")
    invitation.subject = "Our own invitation subject"
    invitation.save()
    migration.rebrand_defaults(apps, SimpleNamespace(connection=connection))
    row.refresh_from_db()
    invitation.refresh_from_db()
    assert "Instantlify" in row.subject and "Nemio" not in row.body
    assert invitation.subject == "Our own invitation subject"
    assert DEFAULT_BRANDING["brand_name"] == "Instantlify"


@pytest.mark.django_db
@pytest.mark.parametrize("prefix", ["instantlify", "nemio"])
def test_new_and_existing_dns_records_verify(workspace, prefix):
    branding = WorkspaceBranding.objects.for_workspace(workspace).create(
        workspace=workspace,
        brand_name="Agency",
        custom_domain="portal.example.com",
        verification_token="test-token",
    )

    def resolver(host, kind):
        return (
            [f"{prefix}-verify=test-token"]
            if host == f"_{prefix}-challenge.portal.example.com" and kind == "TXT"
            else []
        )

    assert verify_custom_domain(branding, resolver=resolver)[0]

import hashlib
import json
import time
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.db import DatabaseError, connection, transaction
from django.test import Client
from django.utils import timezone

from apps.platform_ops.models import (
    Control,
    PlatformAudit,
    PlatformInvite,
    PlatformRole,
    SupportSession,
)
from apps.platform_ops.security import blocked, code_at, new_secret, record, verify_otp
from apps.tenants.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def console_host(settings):
    settings.ALLOWED_HOSTS = [*settings.ALLOWED_HOSTS, "ops.localhost"]


@pytest.fixture
def operator(user):
    user.is_staff = True
    user.save()
    return PlatformRole.objects.create(
        user=user, role="owner", otp_secret=new_secret(), otp_confirmed=True
    )


def signed_client(operator, *, proof=True):
    client = Client(HTTP_HOST="ops.localhost")
    client.force_login(operator.user)
    session = client.session
    session["platform_password_at"] = time.time()
    if proof:
        session["platform_mfa"] = {"version": operator.version, "until": time.time() + 1800}
    session.save()
    return client


def test_host_boundary_and_tenant_owner_denied(user, workspace):
    client = Client()
    client.force_login(user)
    assert client.get("/ops/").status_code == 404
    assert client.get("/ops/", HTTP_HOST="ops.localhost").url == "/ops/login/"
    assert client.get("/api/workspaces/", HTTP_HOST="ops.localhost").status_code == 404


def test_superuser_without_platform_role_is_denied(user):
    user.is_staff = user.is_superuser = True
    user.save()
    client = Client(HTTP_HOST="ops.localhost")
    client.force_login(user)
    assert client.get("/ops/").url == "/ops/login/"


def test_mfa_required_and_expired_proof(operator):
    client = signed_client(operator, proof=False)
    assert client.get("/ops/").url == "/ops/mfa/"
    session = client.session
    session["platform_mfa"] = {"version": operator.version, "until": time.time() - 1}
    session.save()
    assert client.get("/ops/").url == "/ops/mfa/"


def test_totp_rfc_vector_replay_and_encrypted_storage(operator):
    # RFC 6238 SHA1 vector at time 59, reduced to six digits.
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    assert code_at(secret, 1) == "287082"
    current = int(time.time()) // 30
    code = code_at(operator.otp_secret, current)
    assert verify_otp(operator.pk, code)
    assert not verify_otp(operator.pk, code)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT otp_secret FROM platform_ops_platformrole WHERE id=%s", [operator.pk]
        )
        assert cursor.fetchone()[0] != operator.otp_secret


def test_mfa_failure_locks_device(operator):
    for _ in range(5):
        assert not verify_otp(operator.pk, "not-a-code")
    assert not verify_otp(operator.pk, code_at(operator.otp_secret, int(time.time()) // 30))


def test_enrollment_then_dashboard(operator):
    operator.otp_confirmed = False
    operator.save()
    client = signed_client(operator, proof=False)
    assert operator.otp_secret in client.get("/ops/mfa/").content.decode()
    response = client.post(
        "/ops/mfa/", {"code": code_at(operator.otp_secret, int(time.time()) // 30)}
    )
    assert response.url == "/ops/"
    assert operator.otp_secret not in client.get("/ops/mfa/").content.decode()
    with patch("redis.Redis.get", return_value=None), patch("redis.Redis.ttl", return_value=-2):
        assert client.get("/ops/").status_code == 200


@pytest.mark.parametrize("role", ["support", "analyst"])
def test_nonowners_cannot_manage_staff_or_global_controls(operator, role):
    operator.role = role
    operator.save()
    client = signed_client(operator)
    assert (
        client.post("/ops/invite/", {"email": "new@example.com", "role": "owner"}).status_code
        == 403
    )
    assert (
        client.post(
            "/ops/control/", {"key": "ai", "disabled": "true", "reason": "Incident"}
        ).status_code
        == 403
    )


def test_support_workspace_control_and_revocation(operator, workspace):
    operator.role = "support"
    operator.save()
    client = signed_client(operator)
    assert (
        client.post(
            "/ops/control/",
            {
                "workspace": str(workspace.pk),
                "key": "workspace",
                "disabled": "true",
                "reason": "Abuse review",
            },
        ).status_code
        == 302
    )
    assert blocked(workspace.pk)
    operator.active = False
    operator.save()
    assert (
        client.post(
            "/ops/control/",
            {
                "workspace": str(workspace.pk),
                "key": "workspace",
                "disabled": "false",
                "reason": "Reset",
            },
        ).url
        == "/ops/login/"
    )
    assert blocked(workspace.pk)


def test_control_audit_and_global_precedence(operator, workspace):
    client = signed_client(operator)
    assert (
        client.post(
            "/ops/control/", {"key": "ai", "disabled": "true", "reason": "Provider incident"}
        ).status_code
        == 302
    )
    Control.objects.create(scope=str(workspace.pk), key="ai", disabled=False, reason="Local")
    assert blocked(workspace.pk, "ai")
    assert PlatformAudit.objects.filter(action="control.changed", detail__key="ai").exists()
    assert (
        client.post("/ops/control/", {"key": "ai", "reason": "Missing action"}).status_code == 403
    )
    assert client.post("/ops/control/", {"workspace": "invalid", "key": "ai"}).status_code == 404


def test_last_owner_and_old_session_version(operator):
    client = signed_client(operator)
    assert (
        client.post(
            "/ops/staff/", {"id": operator.pk, "role": "analyst", "active": "false"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/ops/staff/", {"id": operator.pk, "role": "owner", "active": "true"}
        ).status_code
        == 302
    )
    assert client.get("/ops/").url == "/ops/mfa/"


def test_audit_queryset_cannot_modify_or_delete(operator):
    entry = record(operator.user, "test.action")
    for operation in [
        lambda: PlatformAudit.objects.filter(pk=entry.pk).update(action="altered"),
        lambda: PlatformAudit.objects.filter(pk=entry.pk).delete(),
    ]:
        with pytest.raises(DatabaseError), transaction.atomic():
            operation()
    entry.refresh_from_db()
    assert entry.action == "test.action"


def test_invitation_email_bound_and_single_use(operator):
    invitee = User.objects.create_user(
        username="support-invitee", email="support@example.com", password="correct-password-long"
    )
    PlatformInvite.objects.create(
        email=invitee.email,
        role="support",
        digest=hashlib.sha256(b"test-token").hexdigest(),
        expires_at=timezone.now() + timedelta(hours=1),
    )
    client = Client(HTTP_HOST="ops.localhost")
    assert (
        client.post(
            "/ops/accept/",
            {"token": "test-token", "username": "owner", "password": "A-very-long-password42"},
        ).status_code
        == 200
    )
    assert not PlatformRole.objects.filter(user=invitee).exists()
    assert (
        client.post(
            "/ops/accept/",
            {
                "token": "test-token",
                "username": invitee.username,
                "password": "correct-password-long",
            },
        ).status_code
        == 302
    )
    assert not PlatformRole.objects.get(user=invitee).otp_confirmed
    assert (
        client.post(
            "/ops/accept/",
            {
                "token": "test-token",
                "username": invitee.username,
                "password": "correct-password-long",
            },
        ).status_code
        == 200
    )


def test_support_session_banner_expiry_and_operator_binding(operator, workspace):
    client = signed_client(operator)
    response = client.post(
        "/ops/support/", {"workspace": workspace.pk, "reason": "Customer requested help"}
    )
    assert response.status_code == 302
    assert b"SUPPORT VIEW" in client.get(response.url).content
    support = SupportSession.objects.get()
    assert PlatformAudit.objects.filter(action="support.viewed").exists()
    support.expires_at = timezone.now() - timedelta(seconds=1)
    support.save()
    assert client.get(response.url).status_code == 404


def test_ip_network_uses_remote_addr_not_forwarded_header(operator, settings):
    settings.PLATFORM_ADMIN_NETWORKS = ["10.0.0.0/8"]
    settings.TRUSTED_PROXY_DEPTH = 0
    client = signed_client(operator)
    assert client.get("/ops/", HTTP_X_FORWARDED_FOR="10.1.2.3").status_code == 403


def test_ip_network_reads_the_hop_the_proxy_wrote(operator, settings):
    """Behind one proxy REMOTE_ADDR is the proxy, so the allow-list has to read the
    entry the proxy appended. Anything the caller put in front of it is ignored."""
    settings.PLATFORM_ADMIN_NETWORKS = ["10.0.0.0/8"]
    settings.TRUSTED_PROXY_DEPTH = 1
    client = signed_client(operator)
    assert client.get("/ops/", HTTP_X_FORWARDED_FOR="10.1.2.3").status_code == 200
    # The rightmost entry is the only one the proxy wrote; a prepended office address
    # must not get an outside caller through.
    assert client.get("/ops/", HTTP_X_FORWARDED_FOR="10.1.2.3, 203.0.113.9").status_code == 403
    assert client.get("/ops/", HTTP_X_FORWARDED_FOR="203.0.113.9").status_code == 403


def test_login_lockout_is_per_client_not_per_proxy(settings):
    """At depth 0 every proxied request shares one bucket, so ten failures from anywhere
    lock every operator out. Counting the forwarded hop keeps the bucket per caller."""
    settings.TRUSTED_PROXY_DEPTH = 1
    client = Client(HTTP_HOST="ops.localhost")
    attacker = {"HTTP_X_FORWARDED_FOR": "203.0.113.9"}
    for _ in range(11):
        client.post("/ops/login/", {"username": "missing", "password": "wrong"}, **attacker)
    assert (
        client.post(
            "/ops/login/", {"username": "missing", "password": "wrong"}, **attacker
        ).status_code
        == 429
    )
    assert (
        client.post(
            "/ops/login/",
            {"username": "other", "password": "wrong"},
            HTTP_X_FORWARDED_FOR="198.51.100.4",
        ).status_code
        == 200
    )


def test_csrf_protects_controls(operator):
    client = Client(enforce_csrf_checks=True, HTTP_HOST="ops.localhost")
    client.force_login(operator.user)
    assert client.post("/ops/control/", {"key": "ai", "disabled": "true"}).status_code == 403


def test_login_throttling():
    client = Client(HTTP_HOST="ops.localhost")
    for _ in range(10):
        assert (
            client.post("/ops/login/", {"username": "missing", "password": "wrong"}).status_code
            == 200
        )
    assert (
        client.post("/ops/login/", {"username": "missing", "password": "wrong"}).status_code == 429
    )


def test_suspension_stops_tenant_api_and_worker(operator, workspace, client):
    from apps.channels.models import ChannelConnection, Delivery
    from apps.channels.tasks import send_delivery

    channel = ChannelConnection.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider="instagram",
        external_account_id="ops-test",
        display_name="Ops test",
        access_token="fake",
        is_test=True,
        expires_at=timezone.now() + timedelta(days=1),
    )
    delivery = Delivery.objects.for_workspace(workspace).create(
        workspace=workspace,
        connection=channel,
        recipient_id="customer",
        idempotency_key="paused",
        payload=json.dumps({"text": "Hello"}),
        available_at=timezone.now(),
    )
    Control.objects.create(
        scope=str(workspace.pk), key="workspace", disabled=True, reason="Incident"
    )
    assert client.get(f"/api/workspaces/{workspace.pk}/conversations/").status_code == 403
    with patch("apps.channels.tasks.adapter_for") as adapter:
        send_delivery(str(workspace.pk), str(delivery.pk))
        adapter.assert_not_called()
    delivery.refresh_from_db()
    assert delivery.status == "pending"


def test_ai_and_integration_factories_honor_controls(workspace):
    from apps.agents.models import AgentConfig
    from apps.agents.providers import provider_for
    from apps.channels.transport import ProviderError

    config = AgentConfig.objects.for_workspace(workspace).create(workspace=workspace, is_test=True)
    Control.objects.create(scope="", key="ai", disabled=True, reason="Incident")
    with pytest.raises(ProviderError, match="platform_paused"):
        provider_for(config)


def test_revenue_normalizes_annual_and_excludes_metered():
    from apps.platform_ops.metrics import monthly_amounts

    result = monthly_amounts(
        {
            "items": {
                "data": [
                    {
                        "quantity": 2,
                        "price": {
                            "currency": "usd",
                            "unit_amount": 12000,
                            "recurring": {"interval": "year"},
                        },
                    },
                    {
                        "price": {
                            "currency": "usd",
                            "unit_amount": 10,
                            "recurring": {"usage_type": "metered"},
                        }
                    },
                ]
            }
        }
    )
    assert result["usd"] == Decimal("2000")


@pytest.mark.parametrize(
    "key,control",
    [
        ("agent-reply:test", "ai"),
        ("voice:test", "ai"),
        ("flow:test", "automations"),
        ("flow:test", "automation:00000000-0000-0000-0000-000000000001"),
    ],
)
def test_queued_generated_messages_honor_pauses(workspace, key, control):
    from apps.channels.models import ChannelConnection, Delivery
    from apps.channels.tasks import send_delivery

    channel = ChannelConnection.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider="instagram",
        external_account_id="pause-generated",
        display_name="Test",
        access_token="fake",
        is_test=True,
        expires_at=timezone.now() + timedelta(days=1),
    )
    item = Delivery.objects.for_workspace(workspace).create(
        workspace=workspace,
        connection=channel,
        recipient_id="test",
        idempotency_key=key,
        payload=json.dumps(
            {"text": "Hello", "automation_id": "00000000-0000-0000-0000-000000000001"}
        ),
        available_at=timezone.now(),
    )
    Control.objects.create(scope=str(workspace.pk), key=control, disabled=True, reason="Test pause")
    with patch("apps.channels.tasks.adapter_for") as adapter:
        send_delivery(str(workspace.pk), str(item.pk))
        adapter.assert_not_called()
    item.refresh_from_db()
    assert item.status == "pending"


def test_metrics_are_scoped_and_context_resets(workspace):
    from apps.platform_ops.metrics import increment, workspace_metrics
    from apps.platform_ops.models import DailyMetric

    with workspace_metrics(workspace.pk):
        increment("meta.calls")
    increment("meta.calls")
    assert DailyMetric.objects.get(name="meta.calls").value == 2
    assert DailyMetric.objects.get(name="meta.calls:" + str(workspace.pk)).value == 1


def test_invite_revocation(operator):
    item = PlatformInvite.objects.create(
        email="staff@example.com",
        role="support",
        digest="a" * 64,
        expires_at=timezone.now() + timedelta(hours=1),
    )
    assert signed_client(operator).post("/ops/invite/revoke/", {"id": item.pk}).status_code == 302
    item.refresh_from_db()
    assert item.expires_at <= timezone.now()
    assert PlatformAudit.objects.filter(action="staff.invite_revoked").exists()


def test_recovery_invalidates_old_proofs(operator):
    from io import StringIO

    from django.core.management import call_command

    client = signed_client(operator)
    call_command(
        "reset_platform_mfa", operator.user.username, reason="Verified recovery", stdout=StringIO()
    )
    operator.refresh_from_db()
    assert not operator.otp_confirmed and not operator.otp_secret
    assert client.get("/ops/").url == "/ops/mfa/"
    assert PlatformAudit.objects.filter(action="staff.mfa_reset").exists()


def test_dashboard_paginates_and_sorts_all_workspaces(operator):
    from apps.tenants.models import Workspace

    Workspace.objects.bulk_create([Workspace(name=f"Ops paging {i:02d}") for i in range(28)])
    client = signed_client(operator)
    with patch("redis.Redis.get", return_value=None), patch("redis.Redis.ttl", return_value=-2):
        response = client.get("/ops/?q=Ops+paging&page=2&sort=cost")
    assert response.status_code == 200
    assert len(response.context["rows"]) == 3


def test_subscription_sync_and_churn_baseline(workspace, settings):
    from apps.billing.services import account_for
    from apps.platform_ops.metrics import revenue_metrics
    from apps.platform_ops.models import SubscriptionSnapshot
    from apps.platform_ops.tasks import sync_subscriptions

    account = account_for(workspace.pk)
    account.subscription_id = "sub_ops_test"
    account.save()
    settings.STRIPE_SECRET_KEY = "fake-key"
    snapshot = {
        "status": "active",
        "items": {
            "data": [
                {
                    "price": {
                        "currency": "usd",
                        "unit_amount": 2500,
                        "recurring": {"interval": "month"},
                    }
                }
            ]
        },
    }
    with patch("apps.platform_ops.tasks.stripe.Subscription.retrieve", return_value=snapshot):
        sync_subscriptions()
    assert SubscriptionSnapshot.objects.get().monthly_cents == 2500
    assert revenue_metrics()["churn"] is None
    SubscriptionSnapshot.objects.create(
        workspace=workspace,
        day=timezone.now().date() - timedelta(days=30),
        currency="usd",
        monthly_cents=2500,
        status="active",
    )
    assert revenue_metrics()["churn"] == "0.0%"


def test_console_forms_submit_with_a_real_origin(user):
    """A `no-referrer` policy makes browsers send `Origin: null`, which the CSRF origin
    check rejects. The console must send a policy that keeps same-origin form posts alive."""
    client = Client(enforce_csrf_checks=True, HTTP_HOST="ops.localhost")
    page = client.get("/ops/login/")
    assert page["Referrer-Policy"] == "same-origin"
    token = page.cookies["csrftoken"].value
    body = {"username": "owner", "password": "wrong", "csrfmiddlewaretoken": token}
    assert client.post("/ops/login/", body, HTTP_ORIGIN="null").status_code == 403
    assert client.post("/ops/login/", body, HTTP_ORIGIN="http://ops.localhost").status_code != 403


def test_dashboard_renders_one_tab_at_a_time(operator):
    client = signed_client(operator)
    with patch("redis.Redis.get", return_value=None), patch("redis.Redis.ttl", return_value=-2):
        overview = client.get("/ops/")
        team = client.get("/ops/?tab=team")
        bogus = client.get("/ops/?tab=nope")
    assert overview.context["tab"] == "overview" and bogus.context["tab"] == "overview"
    assert b"Platform overview" in overview.content
    assert b"Invite staff" not in overview.content
    assert team.context["tab"] == "team"
    assert b"Invite staff" in team.content and b"Platform overview" not in team.content
    assert b'href="/ops/?tab=team" class="nav-item active"' in team.content


def test_revenue_tab_lists_plan_distribution_trials_and_past_due(operator, workspace):
    from apps.billing.services import account_for
    from apps.tenants.services import create_workspace
    from tests.conftest import price_for

    trial = account_for(workspace.pk)
    trial.plan_price = price_for("pro", "annual")
    trial.billing_interval, trial.status = "annual", "trialing"
    trial.trial_ends_at = timezone.now() + timedelta(days=3)
    trial.save()
    late = account_for(create_workspace(operator.user, "Late payer").pk)
    late.plan_price = price_for("starter")
    late.billing_interval, late.status = "monthly", "past_due"
    late.save()
    client = signed_client(operator)
    with patch("redis.Redis.get", return_value=None), patch("redis.Redis.ttl", return_value=-2):
        response = client.get("/ops/?tab=revenue")
    body = response.content.decode()
    rows = [(p["plan"], p["billing_interval"], p["status"]) for p in response.context["plans"]]
    assert rows == [("pro", "annual", "trialing"), ("starter", "monthly", "past_due")]
    assert list(response.context["trials"]) == [trial]
    assert list(response.context["past_due"]) == [late]
    assert "Trials ending" in body and "Late payer" in body


def test_every_console_tab_renders(operator, workspace):
    """Each sidebar entry, and each sub-section within a module, renders its own body
    rather than falling through to a placeholder."""
    from apps.platform_ops.views import TABS

    client = signed_client(operator)
    for tab in TABS:
        response = client.get(f"/ops/?tab={tab}")
        assert response.status_code == 200, tab
        body = response.content.decode()
        assert f'href="/ops/?tab={tab}" class="nav-item active"' in body or tab in {
            "billing_audit"
        }, tab
        assert "Return to Dashboard" not in body, tab
    for tab, subs in {
        "ai_credits": ["transactions", "balances", "usage", "pricing"],
        "segments": ["multi"],
        "blog": ["analytics"],
        "support": ["support_queue", "bugs"],
        "notifications": ["popups", "strips"],
    }.items():
        for sub in subs:
            assert client.get(f"/ops/?tab={tab}&sub={sub}").status_code == 200, f"{tab}/{sub}"


def test_settings_endpoint_stores_https_url_only(operator):
    from apps.platform_ops.models import PlatformSetting

    client = signed_client(operator)
    assert (
        client.post("/ops/settings/", {"email_automation_url": "http://plain.example"}).status_code
        == 403
    )
    assert client.post("/ops/settings/", {"email_automation_url": "notaurl"}).status_code == 403
    response = client.post("/ops/settings/", {"email_automation_url": "https://hooks.example/send"})
    assert response.url == "/ops/?tab=settings&saved=1"
    assert PlatformSetting.get("email_automation_url") == "https://hooks.example/send"
    assert "https://hooks.example/send" in client.get("/ops/?tab=settings").content.decode()


def test_ai_credits_tab_reports_dollars_from_a_cent_ledger(operator, workspace):
    """Balances and the rate card are stored in cents; the console must not print a cent
    figure with a dollar sign in front of it."""
    from apps.billing.models import AICreditBalance, AICreditTransaction, ModelPricingRate

    AICreditBalance.objects.create(
        workspace=workspace, balance_cents=Decimal("12000"), auto_topup_enabled=True
    )
    rate = ModelPricingRate.objects.create(
        model_pattern="gpt-5%", label="OpenAI (GPT-5)", our_input=1250, real_input=125
    )
    AICreditTransaction.objects.create(
        workspace=workspace,
        key="topup-1",
        type="topup",
        amount_cents=Decimal("1000"),
        remaining_balance_cents=Decimal("12000"),
        description="Manual top-up",
    )
    AICreditTransaction.objects.create(
        workspace=workspace,
        key="usage-1",
        type="usage",
        amount_cents=Decimal("-22"),
        real_cost_cents=Decimal("2"),
        remaining_balance_cents=Decimal("11978"),
        model="gpt-5",
        tokens_in=17654,
        tokens_out=18,
        rate=rate,
    )
    client = signed_client(operator)
    overview = client.get("/ops/?tab=ai_credits").content.decode()
    assert "$10.00" in overview  # 1000 cents purchased
    assert "$119.78" in overview  # remaining balance after usage
    balances = client.get("/ops/?tab=ai_credits&sub=balances").content.decode()
    assert "$120.00" in balances
    pricing = client.get("/ops/?tab=ai_credits&sub=pricing").content.decode()
    assert "$12.5" in pricing and "10.0x" in pricing
    usage = client.get("/ops/?tab=ai_credits&sub=usage").content.decode()
    assert "gpt-5" in usage and "17672 tokens" in usage.replace(",", "")

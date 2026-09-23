"""Users page (2.5.5): a ban is a cascade, and every action is audited."""

import time
from unittest.mock import patch

import pytest
from django.test import Client
from rest_framework.test import APIClient

from apps.platform_ops import accounts
from apps.platform_ops.models import Control, PlatformAudit, PlatformRole, PlatformSetting
from apps.platform_ops.security import blocked, new_secret
from apps.tenants.models import User

pytestmark = pytest.mark.django_db

PASSWORD = "A-very-long-password42"


@pytest.fixture(autouse=True)
def console_host(settings):
    settings.ALLOWED_HOSTS = [*settings.ALLOWED_HOSTS, "ops.localhost"]


def staff(role="owner", email="ops@example.com"):
    person = User.objects.create_user(username=email, email=email, password=PASSWORD, is_staff=True)
    return PlatformRole.objects.create(
        user=person, role=role, otp_secret=new_secret(), otp_confirmed=True
    )


def console(operator):
    client = Client(HTTP_HOST="ops.localhost")
    client.force_login(operator.user)
    session = client.session
    session["platform_password_at"] = time.time()
    session["platform_mfa"] = {"version": operator.version, "until": time.time() + 1800}
    session.save()
    return client


def test_banned_user_cannot_sign_in_by_password_or_token(user, workspace):
    anonymous = Client()
    login = {"email": user.email, "password": PASSWORD}
    assert (
        anonymous.post("/api/auth/login/", login, content_type="application/json").status_code
        == 200
    )
    accounts.ban_user(user, operator=staff().user, reason="Spam")
    assert (
        anonymous.post("/api/auth/login/", login, content_type="application/json").status_code
        != 200
    )
    assert (
        anonymous.post("/api/auth/token/", login, content_type="application/json").status_code
        != 200
    )


def test_an_open_session_stops_working_after_a_ban(user, workspace):
    session = Client()
    session.force_login(user, backend="apps.tenants.auth.BanAwareBackend")
    assert session.get("/api/auth/me/").status_code == 200
    accounts.ban_user(user, operator=staff().user, reason="Spam")
    assert session.get("/api/auth/me/").status_code in {401, 403}


def test_a_bearer_token_is_refused_after_a_ban(user, workspace):
    from rest_framework_simplejwt.tokens import RefreshToken

    access = str(RefreshToken.for_user(user).access_token)
    bearer = APIClient()
    bearer.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    assert bearer.get("/api/auth/me/").status_code == 200
    accounts.ban_user(user, operator=staff().user, reason="Spam")
    # DRF answers 403 rather than 401 because session auth is the first authenticator.
    assert bearer.get("/api/auth/me/").status_code in {401, 403}


def test_ban_blacklists_refresh_tokens(user):
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
    from rest_framework_simplejwt.tokens import RefreshToken

    RefreshToken.for_user(user)
    accounts.ban_user(user, operator=staff().user, reason="Chargeback fraud")
    assert BlacklistedToken.objects.filter(token__user=user).count() == 1


def test_ban_pauses_owned_workspaces_and_unban_lifts_only_its_own_pauses(user, workspace):
    from apps.tenants.services import create_workspace

    second = create_workspace(user, "Second")
    # An operator already suspended this workspace for an unrelated reason.
    Control.objects.create(scope=str(second.pk), key="workspace", reason="Legal hold")
    operator = staff().user

    paused = accounts.ban_user(user, operator=operator, reason="Spam")
    assert paused == [str(workspace.pk)]
    assert blocked(workspace.pk) and blocked(second.pk)
    assert Control.objects.get(scope=str(second.pk)).reason == "Legal hold"

    accounts.unban_user(user, operator=operator)
    assert not blocked(workspace.pk)
    # The independent suspension is not the ban's to lift.
    assert blocked(second.pk)


def test_a_banned_owners_automation_step_is_skipped(user, workspace):
    from apps.platform_ops.security import pause_guard

    calls = []

    @pause_guard("automations")
    def step(workspace_id):
        calls.append(workspace_id)

    operator = staff().user
    step(str(workspace.pk))
    accounts.ban_user(user, operator=operator, reason="Spam")
    step(str(workspace.pk))
    accounts.unban_user(user, operator=operator)
    step(str(workspace.pk))
    assert calls == [str(workspace.pk), str(workspace.pk)]


def test_ban_requires_a_reason_and_refuses_superusers(user):
    with pytest.raises(ValueError):
        accounts.ban_user(user, operator=staff().user, reason="  ")
    user.is_superuser = True
    user.save()
    with pytest.raises(ValueError):
        accounts.ban_user(user, operator=User.objects.get(email="ops@example.com"), reason="x")


def test_console_ban_is_audited_and_forbidden_to_analysts(user, workspace):
    owner = staff()
    analyst = staff("analyst", "analyst@example.com")
    assert (
        console(analyst).post(f"/ops/users/{user.pk}/ban/", {"reason": "Spam"}).status_code == 403
    )
    user.refresh_from_db()
    assert not user.is_banned

    assert console(owner).post(f"/ops/users/{user.pk}/ban/", {"reason": "Spam"}).status_code == 302
    user.refresh_from_db()
    assert user.is_banned and user.ban_reason == "Spam"
    entry = PlatformAudit.objects.get(action="user.banned")
    assert entry.detail["target"] == str(user.pk) and entry.detail["reason"] == "Spam"
    # An operator cannot lock themselves out.
    assert (
        console(owner).post(f"/ops/users/{owner.user.pk}/ban/", {"reason": "x"}).status_code == 403
    )


def test_email_needs_a_configured_endpoint_and_posts_the_documented_shape(user):
    owner = staff()
    client = console(owner)
    body = {"subject": "Hello", "message": "Your account"}
    response = client.post(f"/ops/users/{user.pk}/email/", body)
    assert response.status_code == 403 and b"Settings" in response.content

    PlatformSetting.objects.create(key="email_automation_url", value="https://hooks.example/send")
    with patch("apps.channels.transport._request") as sent:
        assert client.post(f"/ops/users/{user.pk}/email/", body).status_code == 302
    payload = sent.call_args.kwargs["json"]
    assert set(payload) == {"operator_id", "target_user_id", "target_email", "subject", "message"}
    assert payload["target_email"] == user.email and payload["operator_id"] == str(owner.user.pk)
    assert PlatformAudit.objects.filter(action="user.emailed").exists()


def test_create_user_matches_signup_and_rejects_duplicates():
    owner = staff()
    client = console(owner)
    form = {"name": "Rae", "email": "rae@example.com", "password": PASSWORD, "workspace": "Rae Co"}
    assert client.post("/ops/users/create/", form).status_code == 302
    created = User.objects.get(email="rae@example.com")
    assert created.check_password(PASSWORD)
    from apps.tenants.models import Membership

    assert Membership.all_objects.get(user=created, role="owner").workspace.name == "Rae Co"
    assert client.post("/ops/users/create/", form).status_code == 403
    assert (
        client.post(
            "/ops/users/create/", {**form, "email": "weak@example.com", "password": "123"}
        ).status_code
        == 403
    )


def test_users_tab_filters_and_shows_history(user, workspace):
    owner = staff()
    accounts.ban_user(user, operator=owner.user, reason="Spam")
    client = console(owner)
    with patch("redis.Redis.get", return_value=None), patch("redis.Redis.ttl", return_value=-2):
        banned = client.get("/ops/?tab=users&status=banned").content.decode()
        active = client.get("/ops/?tab=users&status=active").content.decode()
        history = client.get(f"/ops/?tab=users&sub=history-{user.pk}").content.decode()
    assert user.email in banned and "Spam" in banned
    assert user.email not in active
    assert "user.banned" in history

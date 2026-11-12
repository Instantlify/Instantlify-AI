import re
from unittest.mock import patch

import pytest
from django.core import mail
from rest_framework.test import APIClient

from apps.tenants.magic_link import make_token

pytestmark = pytest.mark.django_db


def token_from_mail():
    return re.search(r"#token=(\S+)", mail.outbox[-1].body).group(1)


def test_link_signs_in_once(user):
    anon = APIClient()
    res = anon.post("/api/auth/magic-link/", {"email": "OWNER@example.com"}, format="json")
    assert res.status_code == 200 and len(mail.outbox) == 1
    token = token_from_mail()
    verified = anon.post("/api/auth/magic-link/verify/", {"token": token}, format="json")
    assert verified.status_code == 200 and verified.json()["email"] == "owner@example.com"
    assert anon.get("/api/auth/me/").status_code == 200
    # Signing in changed last_login, so the same link no longer works.
    again = APIClient().post("/api/auth/magic-link/verify/", {"token": token}, format="json")
    assert again.status_code == 400


def test_unknown_email_gets_the_same_answer_and_no_mail():
    res = APIClient().post("/api/auth/magic-link/", {"email": "nobody@example.com"}, format="json")
    assert res.status_code == 200 and "If an account exists" in res.json()["detail"]
    assert mail.outbox == []


def test_expired_forged_and_banned_tokens_fail(user):
    token = make_token(user)
    import time

    later = time.time() + 16 * 60
    with patch("django.core.signing.time.time", return_value=later):
        assert (
            APIClient()
            .post("/api/auth/magic-link/verify/", {"token": token}, format="json")
            .status_code
            == 400
        )
    assert (
        APIClient()
        .post("/api/auth/magic-link/verify/", {"token": "forged"}, format="json")
        .status_code
        == 400
    )
    user.is_banned = True
    user.save()
    assert (
        APIClient()
        .post("/api/auth/magic-link/verify/", {"token": make_token(user)}, format="json")
        .status_code
        == 400
    )


def test_resend_cooldown_is_case_insensitive_and_generic(user):
    client = APIClient()
    first = client.post("/api/auth/magic-link/", {"email": user.email})
    again = client.post("/api/auth/magic-link/", {"email": user.email.upper()})
    unknown = client.post("/api/auth/magic-link/", {"email": "unknown@example.com"})
    assert first.json() == again.json() == unknown.json()
    assert first.json()["resend_after"] == 60
    assert len(mail.outbox) == 1
    from django.core.cache import cache

    cache.clear()
    assert client.post("/api/auth/magic-link/", {"email": user.email}).status_code == 200
    assert len(mail.outbox) == 2


def test_broker_failure_returns_retry_guidance_for_known_and_unknown(user):
    with patch("apps.tenants.tasks.deliver_magic_link.delay", side_effect=OSError("offline")):
        known = APIClient().post("/api/auth/magic-link/", {"email": user.email})
        unknown = APIClient().post("/api/auth/magic-link/", {"email": "unknown@example.com"})
    assert known.status_code == unknown.status_code == 503
    assert known.json() == unknown.json()
    assert APIClient().post("/api/auth/magic-link/", {"email": user.email}).status_code == 200
    assert len(mail.outbox) == 1


def test_delivery_failure_is_logged_and_retried_without_token_or_address(user, caplog):
    from smtplib import SMTPException

    from apps.tenants.tasks import deliver_magic_link

    with patch(
        "apps.tenants.tasks.send_mail", side_effect=[SMTPException("private-address"), 1]
    ) as send:
        deliver_magic_link.apply(args=[user.pk], throw=False).get(propagate=True)
    assert send.call_count == 2
    assert "Magic-link email delivery failed" in caplog.text
    assert "private-address" not in caplog.text
    assert user.email not in caplog.text
    assert "#token=" not in caplog.text


@pytest.mark.parametrize("backend", ["console", "dummy"])
def test_nondelivering_backend_does_not_report_success(user, settings, backend):
    settings.EMAIL_BACKEND = f"django.core.mail.backends.{backend}.EmailBackend"
    known = APIClient().post("/api/auth/magic-link/", {"email": user.email})
    unknown = APIClient().post("/api/auth/magic-link/", {"email": "unknown@example.com"})
    assert known.status_code == unknown.status_code == 503
    assert known.json() == unknown.json()

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
    assert res.status_code == 200 and "If this email" in res.json()["detail"]
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

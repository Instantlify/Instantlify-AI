from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from django.conf import settings
from django.contrib.sessions.models import Session
from rest_framework.test import APIClient

from apps.tenants.sessions import ACTIVITY_KEY

pytestmark = pytest.mark.django_db


def signed_in(user):
    client = APIClient()
    assert client.login(username=user.username, password="A-very-long-password42")
    return client


def test_login_starts_one_hour_session(user):
    client = signed_in(user)
    assert settings.SESSION_COOKIE_AGE == 3600
    assert client.session.get_expiry_age() <= 3600
    assert client.session.get(ACTIVITY_KEY)
    status = client.get("/api/auth/session/").json()
    assert status["authenticated"] is True
    assert 3590 < status["remaining"] <= 3600


def test_idle_user_expires_even_if_background_polling_continues(user):
    client = signed_in(user)
    started = client.session[ACTIVITY_KEY]
    session_key = client.session.session_key
    original_expiry = Session.objects.get(session_key=session_key).expire_date
    for elapsed in [60, 1800, 3599]:
        with patch("apps.tenants.sessions.time", return_value=started + elapsed):
            assert client.get("/api/auth/me/").status_code == 200
            assert client.get("/api/auth/session/").json()["authenticated"] is True
    assert (
        Session.objects.get(session_key=client.session.session_key).expire_date == original_expiry
    )
    with patch("apps.tenants.sessions.time", return_value=started + 3600):
        assert client.get("/api/auth/me/").status_code == 403
        assert client.get("/api/auth/session/").json() == {"authenticated": False}
    assert not Session.objects.filter(session_key=session_key).exists()


def test_real_activity_extends_session_and_delayed_heartbeat_preserves_actual_idle_time(user):
    client = signed_in(user)
    started = client.session[ACTIVITY_KEY]
    with patch("apps.tenants.sessions.time", return_value=started + 1800):
        response = client.post("/api/auth/session/", {"inactive_for": 20}, format="json")
    assert response.status_code == 200
    assert response.json()["remaining"] == 3580
    assert client.session[ACTIVITY_KEY] == started + 1780
    expiry = Session.objects.get(session_key=client.session.session_key).expire_date
    assert expiry == datetime.fromtimestamp(started + 1780 + 3600, UTC)
    with patch("apps.tenants.sessions.time", return_value=started + 3600):
        assert client.get("/api/auth/me/").status_code == 200
    with patch("apps.tenants.sessions.time", return_value=started + 1780 + 3600):
        assert client.post("/api/auth/session/", {}, format="json").status_code == 403


def test_an_expired_session_cannot_be_revived_by_activity(user):
    client = signed_in(user)
    started = client.session[ACTIVITY_KEY]
    with patch("apps.tenants.sessions.time", return_value=started + 3601):
        assert client.post("/api/auth/session/", {}, format="json").status_code == 403
    assert "_auth_user_id" not in client.session


def test_activity_is_csrf_protected_and_rejects_invalid_timestamps(user):
    client = APIClient(enforce_csrf_checks=True)
    assert client.login(username=user.username, password="A-very-long-password42")
    assert client.post("/api/auth/session/", {}).status_code == 403
    token = client.get("/api/auth/csrf/").json()["csrfToken"]
    for age in [-1, 61]:
        assert (
            client.post(
                "/api/auth/session/", {"inactive_for": age}, HTTP_X_CSRFTOKEN=token
            ).status_code
            == 400
        )
    assert client.post("/api/auth/session/", {}, HTTP_X_CSRFTOKEN=token).status_code == 200


def test_existing_session_adopts_idle_policy_without_polling_extensions(user):
    client = signed_in(user)
    session = client.session
    del session[ACTIVITY_KEY]
    session.save()
    assert client.get("/api/auth/session/").status_code == 200
    assert client.session[ACTIVITY_KEY]
    assert client.session.get_expiry_age() <= 3600

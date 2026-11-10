from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.tenants.models import ProfilePhoto, User

pytestmark = pytest.mark.django_db
PNG = __import__("base64").b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3ioAAAAASUVORK5CYII="
)


def test_email_change_requires_reverification_and_validates_format(client, user):
    user.email_verified_at = timezone.now()
    user.save(update_fields=["email_verified_at"])
    with patch("apps.tenants.verification.send_verification") as verify:
        response = client.patch("/api/auth/me/", {"email": "new@example.com"}, format="json")
    assert response.status_code == 200 and not response.json()["email_verified"]
    user.refresh_from_db()
    assert user.email == "new@example.com" and user.email_verified_at is None
    verify.assert_called_once()
    assert (
        client.patch("/api/auth/me/", {"email": "not an email"}, format="json").status_code == 400
    )
    assert client.patch("/api/auth/me/", {"name": " "}, format="json").status_code == 400


def test_profile_photo_is_persisted_private_and_removable(client, user):
    response = client.patch(
        "/api/auth/me/",
        {"name": "Alex", "photo": SimpleUploadedFile("avatar.png", PNG, content_type="image/png")},
        format="multipart",
    )
    assert response.status_code == 200, response.content
    url = response.json()["photo_url"]
    assert "data" not in response.json()
    assert client.get("/api/auth/me/").json()["photo_url"] == url
    image = client.get(url)
    assert image.status_code == 200 and image.content == PNG
    assert image["Content-Type"] == "image/png" and "no-store" in image["Cache-Control"]
    assert APIClient().get(url).status_code == 403
    stranger = User.objects.create_user(
        username="stranger", email="stranger@example.com", password="example-password"
    )
    other = APIClient()
    other.force_authenticate(stranger)
    assert other.get(url).status_code == 404
    assert client.delete("/api/auth/photo/").status_code == 204
    assert not ProfilePhoto.objects.filter(user=user).exists()


def test_invalid_image_or_duplicate_email_does_not_partially_update_profile(client, user):
    User.objects.create_user(
        username="other", email="other@example.com", password="example-password"
    )
    before = user.first_name
    response = client.patch(
        "/api/auth/me/",
        {
            "name": "Changed",
            "email": "other@example.com",
            "photo": SimpleUploadedFile("avatar.png", PNG, content_type="image/png"),
        },
        format="multipart",
    )
    assert response.status_code == 400
    user.refresh_from_db()
    assert user.first_name == before and not ProfilePhoto.objects.filter(user=user).exists()
    response = client.patch(
        "/api/auth/me/",
        {
            "photo": SimpleUploadedFile(
                "attack.svg", b"<svg><script>alert(1)</script></svg>", content_type="image/svg+xml"
            )
        },
        format="multipart",
    )
    assert response.status_code == 400


def test_password_change_enforces_policy_revokes_refresh_and_preserves_current_session(user):
    current, other = APIClient(), APIClient()
    for client in (current, other):
        client.force_login(user, backend="apps.tenants.auth.BanAwareBackend")
    token = str(RefreshToken.for_user(user))
    assert (
        current.post("/api/auth/password/", {"password": "short123"}, format="json").status_code
        == 400
    )
    assert (
        current.post("/api/auth/password/", {"password": "123456789012"}, format="json").status_code
        == 400
    )
    assert (
        current.post(
            "/api/auth/password/", {"password": "Quartz!River92Cloud"}, format="json"
        ).status_code
        == 200
    )
    assert current.get("/api/auth/me/").status_code == 200
    assert other.get("/api/auth/me/").status_code == 403
    assert (
        APIClient().post("/api/auth/token/refresh/", {"refresh": token}, format="json").status_code
        == 401
    )

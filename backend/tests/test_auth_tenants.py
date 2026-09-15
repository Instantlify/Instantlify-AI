import pytest
from django.db import IntegrityError, transaction
from rest_framework.test import APIClient

from apps.tenants.models import AuditEvent, Membership, OutboxEvent, User
from apps.tenants.services import create_workspace

pytestmark = pytest.mark.django_db


def test_signup_create_workspace_logout_login():
    client = APIClient(enforce_csrf_checks=True)
    token = client.get("/api/auth/csrf/").json()["csrfToken"]
    response = client.post(
        "/api/auth/signup/",
        {"name": "Sam", "email": "Sam@Example.com", "password": "Saffron!River42Cloud"},
        HTTP_X_CSRFTOKEN=token,
    )
    assert response.status_code == 201
    assert response.json()["email"] == "sam@example.com"
    token = client.get("/api/auth/csrf/").json()["csrfToken"]
    response = client.post("/api/workspaces/", {"name": "Acme"}, HTTP_X_CSRFTOKEN=token)
    assert response.status_code == 201
    workspace_id = response.json()["id"]
    assert response.json()["role"] == "owner"
    assert OutboxEvent.objects.for_workspace(workspace_id).count() == 1
    assert AuditEvent.objects.for_workspace(workspace_id).count() == 1
    assert client.post("/api/auth/logout/", HTTP_X_CSRFTOKEN=token).status_code == 204
    assert client.get("/api/auth/me/").status_code == 403
    token = client.get("/api/auth/csrf/").json()["csrfToken"]
    assert (
        client.post(
            "/api/auth/login/",
            {"email": "sam@example.com", "password": "Saffron!River42Cloud"},
            HTTP_X_CSRFTOKEN=token,
        ).status_code
        == 200
    )
    assert client.get("/api/workspaces/").json()["results"][0]["id"] == workspace_id


@pytest.mark.parametrize("path", ["signup", "login"])
def test_auth_endpoints_reject_missing_csrf(path):
    client = APIClient(enforce_csrf_checks=True)
    assert (
        client.post(f"/api/auth/{path}/", {"email": "x@example.com", "password": "abc"}).status_code
        == 403
    )


def test_weak_password_rejected():
    response = APIClient().post(
        "/api/auth/signup/", {"name": "X", "email": "x@example.com", "password": "123"}
    )
    assert response.status_code == 400
    assert not User.objects.filter(email="x@example.com").exists()


def test_email_case_insensitive_unique(user):
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user(username="other", email=user.email.upper(), password="something")


def test_jwt_refresh_rotates_and_revokes(user):
    client = APIClient()
    response = client.post(
        "/api/auth/token/", {"email": user.email, "password": "A-very-long-password42"}
    )
    assert response.status_code == 200
    tokens = response.json()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    assert client.get("/api/auth/me/").status_code == 200
    rotated = client.post("/api/auth/token/refresh/", {"refresh": tokens["refresh"]})
    assert rotated.status_code == 200
    assert (
        client.post("/api/auth/token/refresh/", {"refresh": tokens["refresh"]}).status_code == 401
    )
    assert (
        client.post("/api/auth/token/revoke/", {"refresh": rotated.json()["refresh"]}).status_code
        == 200
    )
    assert (
        client.post("/api/auth/token/refresh/", {"refresh": rotated.json()["refresh"]}).status_code
        == 401
    )


@pytest.mark.parametrize("suffix", ["", "members/", "audit/", "status/", "connections/"])
def test_other_workspace_is_indistinguishable_from_missing(client, workspace, suffix):
    other = User.objects.create_user(username="other", email="other@example.com")
    foreign = create_workspace(other, "Other")
    assert client.get(f"/api/workspaces/{foreign.pk}/{suffix}").status_code == 404
    assert client.get(f"/api/workspaces/{workspace.pk}/{suffix}").status_code == 200
    assert client.get("/api/workspaces/").json()["count"] == 1


def test_unscoped_queries_fail_closed(workspace):
    assert Membership.objects.count() == 0
    assert AuditEvent.objects.count() == 0
    assert Membership.objects.for_workspace(workspace).count() == 1
    with pytest.raises(ValueError):
        Membership.objects.for_workspace(None)


def test_agent_cannot_mutate_or_read_audit(workspace):
    agent = User.objects.create_user(username="agent", email="agent@example.com")
    Membership.objects.for_workspace(workspace).create(
        workspace=workspace, user=agent, role="agent"
    )
    client = APIClient()
    client.force_authenticate(agent)
    assert client.patch(f"/api/workspaces/{workspace.pk}/", {"name": "Hacked"}).status_code == 403
    assert client.get(f"/api/workspaces/{workspace.pk}/audit/").status_code == 403
    assert client.post(f"/api/workspaces/{workspace.pk}/meta/connect/").status_code == 403
    assert client.get(f"/api/workspaces/{workspace.pk}/members/").status_code == 200


def test_owner_can_change_role_but_not_transfer_owner(client, workspace):
    agent = User.objects.create_user(username="agent", email="agent@example.com")
    member = Membership.objects.for_workspace(workspace).create(workspace=workspace, user=agent)
    url = f"/api/workspaces/{workspace.pk}/members/{member.pk}/"
    assert client.patch(url, {"role": "admin"}).status_code == 200
    assert client.patch(url, {"role": "owner"}).status_code == 403
    assert (
        AuditEvent.objects.for_workspace(workspace)
        .filter(action="membership.role_changed")
        .exists()
    )


def test_foreign_workspace_in_body_cannot_redirect_write(client, workspace):
    response = client.patch(
        f"/api/workspaces/{workspace.pk}/", {"name": "Renamed", "workspace": "foreign"}
    )
    assert response.status_code == 200
    workspace.refresh_from_db()
    assert workspace.name == "Renamed"


def test_invalid_role_and_duplicate_membership_rejected(user, workspace):
    with pytest.raises(IntegrityError), transaction.atomic():
        Membership.all_objects.create(workspace=workspace, user=user, role="admin")
    other = User.objects.create_user(username="other", email="other@example.com")
    with pytest.raises(IntegrityError), transaction.atomic():
        Membership.all_objects.create(workspace=workspace, user=other, role="superuser")

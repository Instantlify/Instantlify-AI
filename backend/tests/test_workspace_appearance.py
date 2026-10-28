import base64

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.tenants.models import Membership, User, WorkspaceBranding
from apps.tenants.services import create_workspace

pytestmark = pytest.mark.django_db
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def appearance(**changes):
    return {
        "brand_name": "North Studio",
        "workspace_name": "North workspace",
        "primary_color": "#7C3AED",
        "sidebar_bg_color": "#10244A",
        "sidebar_text_color": "#FFFFFF",
        **changes,
    }


def test_saved_appearance_is_returned_after_reload_and_does_not_change_other_workspaces(
    client, workspace, user
):
    other = create_workspace(user, "Other")
    url = f"/api/workspaces/{workspace.pk}/branding/"
    result = client.put(url, appearance(), format="json")
    assert result.status_code == 200, result.data
    workspace.refresh_from_db()
    assert workspace.name == "North workspace"
    result = client.get(url)
    assert result.data["effective"]["sidebar_bg_color"] == "#10244a"
    assert result.data["own"]["sidebar_text_color"] == "#ffffff"
    listed = client.get("/api/workspaces/").data["results"]
    records = {str(item["id"]): item for item in listed}
    assert records[str(workspace.pk)]["branding"]["primary_color"] == "#7c3aed"
    assert records[str(other.pk)]["branding"]["primary_color"] == "#10244a"
    assert records[str(other.pk)]["branding"]["sidebar_bg_color"] == "#ffffff"


@pytest.mark.parametrize(
    "field,value",
    [("primary_color", "red"), ("sidebar_bg_color", "#abc"), ("sidebar_text_color", "#gggggg")],
)
def test_invalid_colors_are_field_errors_and_do_not_partially_rename_workspace(
    client, workspace, field, value
):
    old_name = workspace.name
    result = client.put(
        f"/api/workspaces/{workspace.pk}/branding/", appearance(**{field: value}), format="json"
    )
    assert result.status_code == 400 and field in result.data
    workspace.refresh_from_db()
    assert workspace.name == old_name
    assert not WorkspaceBranding.objects.for_workspace(workspace).exists()


def test_unreadable_sidebar_text_is_rejected(client, workspace):
    result = client.put(
        f"/api/workspaces/{workspace.pk}/branding/",
        appearance(sidebar_bg_color="#ffffff"),
        format="json",
    )
    assert result.status_code == 400
    assert "sidebar_text_color" in result.data


def test_logo_upload_is_durable_public_image_and_not_embedded_in_workspace_json(client, workspace):
    url = f"/api/workspaces/{workspace.pk}/branding/"
    result = client.put(
        url,
        {**appearance(), "logo": SimpleUploadedFile("logo.png", PNG, content_type="image/png")},
        format="multipart",
    )
    assert result.status_code == 200, result.data
    logo = result.data["logo_url"]
    assert logo.startswith(f"/api/public/workspace-logos/{workspace.pk}/")
    public = APIClient()
    downloaded = public.get(logo)
    assert downloaded.status_code == 200 and downloaded.content == PNG
    assert downloaded["Content-Type"] == "image/png"
    assert downloaded["X-Content-Type-Options"] == "nosniff"
    assert public.get(logo, HTTP_IF_NONE_MATCH=downloaded["ETag"]).status_code == 304
    assert "logo_data" not in client.get(url).data["own"]
    assert client.get(url).data["effective"]["logo_url"] == logo
    # Saving a color without replacing the image keeps the existing asset.
    assert client.put(url, {"primary_color": "#c3ff5c"}, format="json").status_code == 200
    assert public.get(logo).status_code == 200
    assert client.put(url, {"logo_url": ""}, format="json").status_code == 200
    assert public.get(logo).status_code == 404


@pytest.mark.parametrize(
    "data",
    [b"<svg onload='alert(1)'></svg>", b"<html>not an image</html>", b"x" * (5 * 1024 * 1024 + 1)],
    ids=["svg", "html", "oversized"],
)
def test_unsafe_or_oversized_logo_is_rejected(client, workspace, data):
    result = client.put(
        f"/api/workspaces/{workspace.pk}/branding/",
        {**appearance(), "logo": SimpleUploadedFile("logo.png", data, content_type="image/png")},
        format="multipart",
    )
    assert result.status_code == 400 and "logo" in result.data
    assert not WorkspaceBranding.objects.for_workspace(workspace).exists()


def test_agency_appearance_and_logo_are_inherited_until_client_sets_its_own(
    client, workspace, user
):
    result = client.put(
        f"/api/workspaces/{workspace.pk}/branding/",
        {**appearance(), "logo": SimpleUploadedFile("logo.png", PNG, content_type="image/png")},
        format="multipart",
    )
    assert result.status_code == 200
    child = create_workspace(user, "Client")
    child.parent = workspace
    child.save(update_fields=["parent"])
    url = f"/api/workspaces/{child.pk}/branding/"
    assert client.get(url).data["effective"]["sidebar_bg_color"] == "#10244a"
    assert client.get(url).data["effective"]["logo_url"] == result.data["logo_url"]
    assert (
        client.put(
            url, appearance(brand_name="Client", primary_color="#c3ff5c"), format="json"
        ).status_code
        == 200
    )
    assert client.get(url).data["effective"]["logo_url"] == ""
    assert (
        client.get(f"/api/workspaces/{workspace.pk}/branding/").data["effective"]["primary_color"]
        == "#7c3aed"
    )


@pytest.mark.parametrize("role", ["admin", "agent"])
def test_nonowners_cannot_change_appearance_or_upload_logos(workspace, role):
    user = User.objects.create_user(username=role, email=f"{role}@example.com")
    Membership.objects.for_workspace(workspace).create(workspace=workspace, user=user, role=role)
    client = APIClient()
    client.force_authenticate(user)
    result = client.put(f"/api/workspaces/{workspace.pk}/branding/", appearance(), format="json")
    assert result.status_code == 403
    assert not WorkspaceBranding.objects.for_workspace(workspace).exists()

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.platform_ops.models import Announcement, AnnouncementNotification
from apps.tenants.models import User

pytestmark = pytest.mark.django_db


def test_schedule_boundaries_and_background_delivery(client):
    now = timezone.now()
    notice = Announcement.objects.create(
        name="Maintenance",
        is_active=True,
        starts_at=now + timedelta(minutes=1),
        ends_at=now + timedelta(minutes=2),
    )
    assert client.get("/api/notifications/").json()["results"] == []
    with patch("apps.platform_ops.notifications.timezone.now", return_value=notice.starts_at):
        assert client.get("/api/notifications/").json()["unread_count"] == 1
        assert len(client.get("/api/growth/announcements/").json()) == 1
        assert client.get("/api/notifications/").json()["count"] == 1
    with patch("apps.platform_ops.notifications.timezone.now", return_value=notice.ends_at):
        assert client.get("/api/growth/announcements/").json() == []
        feed = client.get("/api/notifications/").json()
        assert feed["results"][0]["expired"]
    notice.delete()
    assert client.get("/api/notifications/").json()["count"] == 1


def test_read_acknowledgement_revision_history_and_isolation(client, user):
    notice = Announcement.objects.create(
        name="Maintenance", is_active=True, type="popup", requires_acknowledgement=True
    )
    item = client.get("/api/notifications/").json()["results"][0]
    assert client.patch("/api/notifications/", {"all_read": True}, format="json").status_code == 204
    receipt = AnnouncementNotification.objects.get(pk=item["id"])
    assert receipt.read_at and not receipt.acknowledged_at
    assert len(client.get("/api/growth/announcements/").json()) == 1
    assert (
        client.patch(
            "/api/notifications/", {"id": item["id"], "acknowledge": True}, format="json"
        ).status_code
        == 204
    )
    assert client.get("/api/growth/announcements/").json() == []
    notice.revision += 1
    notice.title = "Updated maintenance"
    notice.save()
    feed = client.get("/api/notifications/").json()
    assert feed["count"] == 2 and feed["unread_count"] == 1
    other = User.objects.create_user(username="other")
    client.force_authenticate(other)
    assert client.patch("/api/notifications/", {"id": item["id"]}, format="json").status_code == 404
    assert (
        client.patch(
            "/api/notifications/", {"all_read": True, "acknowledge": True}, format="json"
        ).status_code
        == 400
    )


def test_targeting_ownership_and_safe_links(client, workspace):
    Announcement.objects.create(
        name="Targeted", is_active=True, target_pages="settings", link_url="javascript:alert(1)"
    )
    assert client.get("/api/notifications/?section=dashboard").json()["results"] == []
    feed = client.get(f"/api/notifications/?section=settings&workspace_id={workspace.pk}").json()
    assert feed["results"][0]["link_url"] == ""
    stranger = User.objects.create_user(username="stranger")
    client.force_authenticate(stranger)
    assert client.get(f"/api/notifications/?workspace_id={workspace.pk}").status_code == 404
    assert client.get("/api/notifications/?workspace_id=bad").status_code == 400


def test_notification_history_is_paginated(client):
    Announcement.objects.bulk_create(
        [Announcement(name=f"Notice {n}", is_active=True) for n in range(23)]
    )
    feed = client.get("/api/notifications/").json()
    assert feed["count"] == 23 and len(feed["results"]) == 20
    assert len(client.get("/api/notifications/?page=2").json()["results"]) == 3

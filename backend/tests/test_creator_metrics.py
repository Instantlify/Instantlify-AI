from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.channels.models import ChannelConnection
from apps.tools.creator_metrics import refresh_creator_metrics
from apps.tools.models import CreatorKit
from tests.conftest import set_limits

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def analytics_approval(workspace):
    from apps.platform_ops.models import WorkspaceCapability

    return WorkspaceCapability.objects.create(
        workspace=workspace, key="meta_analytics", enabled=True, reason="Test approval"
    )


def connection(workspace):
    return ChannelConnection.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider="instagram",
        external_account_id="ig-metrics",
        display_name="creator.account",
        access_token="private-token",
        is_test=False,
        expires_at=timezone.now() + timedelta(days=40),
        profile={"followers_count": 120},
    )


def create(client, workspace):
    channel = connection(workspace)
    url = f"/api/workspaces/{workspace.pk}/creator-kit/"
    data = {
        "slug": "creator-metrics",
        "name": "Creator",
        "live_connection_ids": [str(channel.pk)],
        "published": True,
    }
    response = client.put(url, data, format="json")
    assert response.status_code == 200, response.content
    return channel, CreatorKit.objects.for_workspace(workspace).get(), url, data


def test_public_connected_counts_are_sourced_not_editable_figures(client, workspace):
    _, _, url, data = create(client, workspace)
    data["statistics"] = [{"label": "Entered audience", "value": "9999999"}]
    assert client.put(url, data, format="json").status_code == 200
    response = client.get("/api/public/creator/creator-metrics/")
    assert response.status_code == 200
    assert response.json()["live_statistics"][0]["value"] == "120"
    assert response.json()["live_statistics"][0]["account"] == "creator.account"
    assert response.json()["statistics"][0]["value"] == "9999999"
    assert "live_connection_ids" not in response.json()
    assert "private-token" not in response.content.decode()


def test_background_refresh_updates_counts_and_schedules_next_hour(client, workspace):
    channel, kit, _, _ = create(client, workspace)
    with patch(
        "apps.tools.creator_metrics.request", return_value={"followers_count": 345}
    ) as fetch:
        refresh_creator_metrics(str(workspace.pk), str(kit.pk))
        refresh_creator_metrics(str(workspace.pk), str(kit.pk))
    fetch.assert_called_once()
    assert fetch.call_args.args[0] == "GET"
    channel.refresh_from_db()
    kit.refresh_from_db()
    assert channel.profile["followers_count"] == 345 and channel.profile["creator_stats_checked_at"]
    assert kit.live_stats_next_at > timezone.now() and kit.live_stats_error == ""


def test_failed_refresh_preserves_last_count(client, workspace):
    channel, kit, _, _ = create(client, workspace)
    with patch("apps.tools.creator_metrics.request", return_value={}):
        refresh_creator_metrics(str(workspace.pk), str(kit.pk))
    channel.refresh_from_db()
    kit.refresh_from_db()
    assert channel.profile["followers_count"] == 120
    assert kit.live_stats_error == "statistics_unavailable"


def test_disabling_during_fetch_prevents_stale_updates(client, workspace):
    channel, kit, url, data = create(client, workspace)

    def disable(*args, **kwargs):
        assert (
            client.put(url, {**data, "live_connection_ids": []}, format="json").status_code == 200
        )
        return {"followers_count": 999}

    with patch("apps.tools.creator_metrics.request", side_effect=disable):
        refresh_creator_metrics(str(workspace.pk), str(kit.pk))
    channel.refresh_from_db()
    assert channel.profile["followers_count"] == 120
    assert client.get("/api/public/creator/creator-metrics/").json()["live_statistics"] == []


def test_downgrade_prevents_provider_refresh_but_allows_disabling(client, workspace):
    _, kit, url, data = create(client, workspace)
    set_limits(workspace, integrations_unlocked=False)
    with patch("apps.tools.creator_metrics.request") as fetch:
        refresh_creator_metrics(str(workspace.pk), str(kit.pk))
    fetch.assert_not_called()
    assert client.put(url, {**data, "live_connection_ids": []}, format="json").status_code == 200


def test_foreign_connected_accounts_cannot_be_published(client, workspace, user):
    from apps.tenants.services import create_workspace

    other = create_workspace(user, "Other creator")
    channel = connection(other)
    response = client.put(
        f"/api/workspaces/{workspace.pk}/creator-kit/",
        {"slug": "creator", "name": "Creator", "live_connection_ids": [str(channel.pk)]},
        format="json",
    )
    assert response.status_code == 400


def test_opt_in_publishes_provider_insights_without_fabricating_unavailable_counts(
    client, workspace
):
    channel, kit, url, data = create(client, workspace)
    assert client.put(url, {**data, "live_insights": True}, format="json").status_code == 200

    def fetch(method, url, **kwargs):
        if not url.endswith("/insights"):
            return {"followers_count": 321, "follows_count": 24, "media_count": 12}
        metric = kwargs["params"]["metric"]
        assert kwargs["params"]["until"] > kwargs["params"]["since"]
        return (
            {"data": [{"name": metric, "total_value": {"value": 987}}]}
            if metric != "views"
            else {"data": []}
        )

    with patch("apps.tools.creator_metrics.request", side_effect=fetch):
        refresh_creator_metrics(str(workspace.pk), str(kit.pk))
    rows = client.get("/api/public/creator/creator-metrics/").json()["live_statistics"]
    assert any(row["label"] == "Instagram posts" and row["value"] == "12" for row in rows)
    assert any(
        row["label"] == "Accounts reached (28 days)" and row["value"] == "987" for row in rows
    )
    assert any(row["label"] == "Views (28 days)" and row["value"] == "Unavailable" for row in rows)
    assert client.put(url, {**data, "live_insights": False}, format="json").status_code == 200
    assert not any(
        "28 days" in row["label"]
        for row in client.get("/api/public/creator/creator-metrics/").json()["live_statistics"]
    )

import json
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.channels.models import ChannelConnection, Delivery


@pytest.mark.django_db
def test_delivery_pages_are_five_newest_first_and_keep_legacy_array(client, workspace):
    channel = ChannelConnection.objects.for_workspace(workspace).create(
        workspace=workspace,
        external_account_id="paging",
        display_name="Paging",
        access_token="",
        expires_at=timezone.now() + timedelta(days=1),
        is_test=True,
    )
    ids = []
    for index in range(12):
        row = Delivery.objects.for_workspace(workspace).create(
            workspace=workspace,
            connection=channel,
            recipient_id=f"recipient-{index}",
            idempotency_key=f"page-{index}",
            payload=json.dumps({}),
            available_at=timezone.now(),
        )
        Delivery.objects.for_workspace(workspace).filter(pk=row.pk).update(
            created_at=timezone.now() + timedelta(seconds=index)
        )
        ids.append(str(row.pk))
    url = f"/api/workspaces/{workspace.pk}/deliveries/"
    found = []
    for page, size in [(1, 5), (2, 5), (3, 2)]:
        response = client.get(url, {"page": page})
        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 12 and len(body["results"]) == size
        found.extend(row["id"] for row in body["results"])
    assert found == list(reversed(ids))
    assert client.get(url, {"page": 4}).status_code == 404
    legacy = client.get(url).json()
    assert isinstance(legacy, list) and len(legacy) == 12

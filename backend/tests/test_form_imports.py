import json
from unittest.mock import patch

import pytest

from apps.crm.models import Conversation, IntegrationConfig, Lead

pytestmark = pytest.mark.django_db


def test_jotform_reimport_matches_contacts_and_preserves_opt_out(client, workspace):
    config = IntegrationConfig.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider="jotform",
        credentials=json.dumps({"api_key": "private"}),
        options={"form_id": "123", "email_question": "2", "name_question": "1", "region": "eu"},
    )
    existing = Lead.objects.for_workspace(workspace).create(
        workspace=workspace, email="old@example.com", opted_out=True, tags=["vip"]
    )
    body = {
        "responseCode": 200,
        "content": [
            {
                "answers": {
                    "1": {"answer": {"first": "A", "last": "Person"}},
                    "2": {"answer": "new@example.com"},
                }
            },
            {"answers": {"2": {"answer": "old@example.com"}}},
            {"answers": {"2": {"answer": "invalid"}}},
        ],
    }
    url = f"/api/workspaces/{workspace.pk}/integrations/{config.pk}/contacts/"
    with patch("apps.crm.form_imports.request", return_value=body) as provider:
        response = client.post(url, {}, format="json")
        assert response.status_code == 200, response.content
        assert response.json() == {"created": 1, "matched_existing": 1, "skipped": 1}
        assert client.post(url, {}, format="json").json()["created"] == 0
    assert provider.call_args.args[1] == "https://eu-api.jotform.com/form/123/submissions"
    assert provider.call_args.kwargs["headers"] == {"APIKEY": "private"}
    assert Lead.objects.for_workspace(workspace).count() == 2
    assert not Conversation.objects.for_workspace(workspace).exists()
    existing.refresh_from_db()
    assert existing.opted_out and existing.tags == ["vip"]


def test_invalid_jotform_region_never_makes_a_provider_request(client, workspace):
    config = IntegrationConfig.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider="jotform",
        credentials=json.dumps({"api_key": "private"}),
        options={"form_id": "123", "email_question": "2", "region": "https://localhost/"},
    )
    with patch("apps.crm.form_imports.request") as provider:
        response = client.post(
            f"/api/workspaces/{workspace.pk}/integrations/{config.pk}/contacts/", {}, format="json"
        )
    assert response.status_code == 400
    provider.assert_not_called()

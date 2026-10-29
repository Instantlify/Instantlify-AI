from unittest.mock import patch

import pytest
from django.test import Client
from rest_framework.test import APIClient

from apps.platform_ops.models import SupportTicket, SupportTicketMessage
from apps.tenants.models import Membership, User
from apps.tenants.services import create_workspace

pytestmark = pytest.mark.django_db


def url(workspace):
    return f"/api/workspaces/{workspace.pk}/support/tickets/"


def test_create_track_reply_and_reopen_ticket(client, workspace, user):
    response = client.post(
        url(workspace),
        {
            "subject": "Automation stuck",
            "body": "The published flow stopped",
            "category": "bug",
            "email": "spoof@example.com",
        },
        format="json",
    )
    assert response.status_code == 201
    ticket = SupportTicket.objects.get()
    assert ticket.reporter == user and ticket.workspace == workspace
    assert ticket.reporter_email == user.email
    SupportTicketMessage.objects.create(
        ticket=ticket, author=user, from_staff=True, body="Please reconnect the channel."
    )
    ticket.status = "resolved"
    ticket.save()
    rows = client.get(url(workspace)).json()
    assert rows[0]["messages"][0]["from_staff"]
    response = client.post(
        f"{url(workspace)}{ticket.pk}/replies/", {"body": "Still stuck"}, format="json"
    )
    assert response.status_code == 201
    ticket.refresh_from_db()
    assert ticket.status == "unresolved" and not ticket.is_read
    assert response.json()["messages"][-1]["body"] == "Still stuck"


def test_tickets_are_private_to_workspace_and_reporter(client, workspace, user):
    other = User.objects.create_user(username="other", email="other@example.com")
    foreign = create_workspace(other, "Other")
    Membership.all_objects.create(workspace=workspace, user=other, role="agent")
    ticket = SupportTicket.objects.create(
        ticket_number="#999",
        reporter=user,
        workspace=workspace,
        subject="Private",
        reporter_email=user.email,
    )
    outsider = APIClient()
    outsider.force_authenticate(other)
    assert outsider.get(url(workspace)).json() == []
    assert (
        outsider.post(f"{url(workspace)}{ticket.pk}/replies/", {"body": "attack"}).status_code
        == 404
    )
    assert client.get(url(foreign)).status_code == 404
    assert client.post(f"{url(foreign)}{ticket.pk}/replies/", {"body": "attack"}).status_code == 404
    assert APIClient().get(url(workspace)).status_code in (401, 403)


def test_ticket_validation(client, workspace):
    assert client.post(url(workspace), {"subject": "", "body": ""}).status_code == 400
    assert (
        client.post(
            url(workspace), {"subject": "Broken", "body": "details", "category": "invalid"}
        ).status_code
        == 400
    )
    assert (
        client.post(url(workspace), {"subject": "Broken", "body": "x" * 10001}).status_code == 400
    )
    response = Client().post(
        "/api/growth/tickets/",
        {"subject": "Help", "email": "invalid"},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert not SupportTicket.objects.exists()


def test_chat_outage_offers_ticket_without_claiming_success():
    from apps.channels.transport import ProviderError

    with patch("apps.platform_ops.support_agent.answer", side_effect=ProviderError("offline")):
        response = Client().post(
            "/api/growth/support-chat/",
            {"message": "What does Nemio do?"},
            content_type="application/json",
        )
    assert response.status_code == 200
    assert "Raise a ticket" in response.json()["reply"]
    assert not SupportTicket.objects.exists()

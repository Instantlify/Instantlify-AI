from smtplib import SMTPAuthenticationError
from unittest.mock import patch

import pytest

from apps.platform_ops.models import EmailTemplate
from apps.tenants.models import AuditEvent, Invitation
from tests.test_team_and_inbound import invite, seats, token_from

pytestmark = pytest.mark.django_db


def test_invitation_email_contains_the_same_usable_link(
    client, workspace, user, mailoutbox, settings
):
    seats(workspace, 3)
    settings.PUBLIC_APP_URL = "https://app.instantlify.example"
    settings.DEFAULT_FROM_EMAIL = "Instantlify <sender@example.com>"
    mailoutbox.clear()
    response = invite(client, workspace, "teammate@example.com")
    assert response.status_code == 201
    assert response.json()["email_sent"] is True
    assert len(mailoutbox) == 1
    email = mailoutbox[0]
    assert email.to == ["teammate@example.com"]
    assert email.from_email == settings.DEFAULT_FROM_EMAIL
    assert workspace.name in email.subject
    assert user.email in email.body
    assert response.json()["accept_url"] in email.body
    assert "seven days" in email.body
    token = token_from(response)
    assert token not in client.get(f"/api/workspaces/{workspace.pk}/invitations/").content.decode()
    assert token not in str(list(AuditEvent.objects.for_workspace(workspace).values()))


def test_smtp_failure_preserves_invitation_and_reports_fallback(client, workspace):
    seats(workspace, 3)
    with patch(
        "django.core.mail.message.EmailMessage.send",
        side_effect=SMTPAuthenticationError(535, b"Rejected"),
    ):
        response = invite(client, workspace, "teammate@example.com")
    assert response.status_code == 201
    assert response.json()["email_sent"] is False
    assert response.json()["accept_url"]
    assert Invitation.objects.for_workspace(workspace).count() == 1


def test_draft_template_does_not_send_email(client, workspace, mailoutbox):
    seats(workspace, 3)
    mailoutbox.clear()
    EmailTemplate.objects.filter(name="workspace-invitation").update(status="draft")
    response = invite(client, workspace, "teammate@example.com")
    assert response.status_code == 201
    assert response.json()["email_sent"] is False
    assert not mailoutbox


def test_plan_rejection_never_sends_invitation(client, workspace, mailoutbox):
    seats(workspace, 1)
    mailoutbox.clear()
    assert invite(client, workspace, "teammate@example.com").status_code == 402
    assert not mailoutbox

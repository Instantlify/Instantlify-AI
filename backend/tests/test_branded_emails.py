import importlib
import re
from html.parser import HTMLParser
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.core import mail
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

from apps.platform_ops.growth import send_transactional_email
from apps.platform_ops.models import EmailTemplate

pytestmark = pytest.mark.django_db

AUTH_EMAILS = [
    (
        "email-verification",
        "/api/auth/verify-email/resend/",
        "/auth/verify/#token=",
        "Verify email address",
    ),
    ("password-reset", "/api/auth/password-reset/", "/auth/reset/#uid=", "Reset password"),
    ("magic-link-signin", "/api/auth/magic-link/", "/auth/magic/#token=", "Sign in"),
]


class Links(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.urls = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.urls.append(dict(attrs).get("href"))


@pytest.mark.parametrize("template,path,fragment,button", AUTH_EMAILS)
def test_auth_emails_use_live_admin_copy_and_branded_html_with_text_fallback(
    user, settings, template, path, fragment, button
):
    settings.PUBLIC_APP_URL = "https://dev.instantlify.com"
    user.first_name = "Alex <script>alert(1)</script>"
    user.save(update_fields=["first_name"])
    EmailTemplate.objects.filter(name=template).update(
        subject="Admin subject for {{ name }}",
        body="Admin-edited message for {{ name }}.\n\n{{ link }}\n\nKeep this link private.",
    )
    response = APIClient().post(path, {"email": user.email})
    assert response.status_code == 200
    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.subject == f"Admin subject for {user.first_name}"
    assert "Admin-edited message" in message.body
    assert message.content_subtype == "plain"
    assert message.from_email == settings.DEFAULT_FROM_EMAIL
    assert message.alternatives[0][1] == "text/html"
    html = message.alternatives[0][0]
    assert "Instantlify" in html and button in html
    assert "Admin-edited message" in html
    assert "Keep this link private." in html
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    url = re.search(r"https://\S+", message.body).group(0)
    assert fragment in url
    assert url in Links(html).urls


@pytest.mark.parametrize("template,path,fragment,button", AUTH_EMAILS)
@pytest.mark.parametrize("unavailable", ["draft", "missing"])
def test_auth_drafts_and_missing_templates_do_not_send_or_reveal_accounts(
    user, template, path, fragment, button, unavailable
):
    if unavailable == "draft":
        EmailTemplate.objects.filter(name=template).update(status="draft")
    else:
        EmailTemplate.objects.filter(name=template).delete()
    known = APIClient().post(path, {"email": user.email})
    unknown = APIClient().post(path, {"email": "unknown@example.com"})
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert mail.outbox == []


def test_verification_seed_preserves_operator_edits_and_draft_status():
    EmailTemplate.objects.filter(name="email-verification").update(
        subject="Operator copy", body="Custom body {{ link }}", status="draft"
    )
    migration = importlib.import_module(
        "apps.platform_ops.migrations.0015_email_verification_template"
    )
    migration.seed(apps, SimpleNamespace(connection=connection))
    template = EmailTemplate.objects.get(name="email-verification")
    assert (template.subject, template.body, template.status) == (
        "Operator copy",
        "Custom body {{ link }}",
        "draft",
    )


def test_unsafe_action_url_is_not_rendered_as_a_button():
    send_transactional_email("password-reset", "test@example.com", {"link": "javascript:alert(1)"})
    assert not any(
        url.startswith("javascript:") for url in Links(mail.outbox[0].alternatives[0][0]).urls
    )


def test_all_transactional_templates_receive_html_without_changing_plain_copy():
    EmailTemplate.objects.create(
        name="probe-html", subject="A note", body="Line one.\n\nLine two.", status="active"
    )
    send_transactional_email("probe-html", "test@example.com")
    assert mail.outbox[0].body == "Line one.\n\nLine two."
    assert "Line one.<br><br>Line two." in mail.outbox[0].alternatives[0][0]


def test_action_link_remains_available_in_plain_text_if_operator_omits_placeholder():
    EmailTemplate.objects.filter(name="password-reset").update(
        body="Your custom reset instructions."
    )
    link = "https://dev.instantlify.com/auth/reset/#uid=MQ&token=example"
    send_transactional_email("password-reset", "test@example.com", {"link": link})
    assert "Your custom reset instructions." in mail.outbox[0].body
    assert link in mail.outbox[0].body
    assert link in Links(mail.outbox[0].alternatives[0][0]).urls


def test_email_change_uses_admin_confirmation_and_old_address_notice(user):
    user.email_verified_at = timezone.now()
    user.save(update_fields=["email_verified_at"])
    old_email = user.email
    EmailTemplate.objects.filter(name="email-change-confirmation").update(
        subject="Confirm new address", body="Confirm it here:\n\n{{ link }}"
    )
    EmailTemplate.objects.filter(name="email-change-notice-current").update(
        subject="Address change notice",
        body="Your address is now {{ new_email }}. Contact {{ support_email }}.",
    )
    client = APIClient()
    client.force_authenticate(user)
    assert client.patch("/api/auth/me/", {"email": "new@example.com"}).status_code == 200
    confirmation = next(m for m in mail.outbox if m.to == ["new@example.com"])
    notice = next(m for m in mail.outbox if m.to == [old_email])
    assert confirmation.subject == "Confirm new address"
    assert "/auth/verify/#token=" in confirmation.body
    assert "Confirm email address" in confirmation.alternatives[0][0]
    assert notice.subject == "Address change notice"
    assert "new@example.com" in notice.body
    assert "Instantlify" in notice.alternatives[0][0]


def test_unverified_old_address_does_not_receive_change_notices(user):
    client = APIClient()
    client.force_authenticate(user)
    assert client.patch("/api/auth/me/", {"email": "new@example.com"}).status_code == 200
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["new@example.com"]

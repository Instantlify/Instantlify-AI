"""Growth-side platform surfaces: signup funnel, marketing analytics, blog, tickets,
the support agent's ticket gate, announcements, promos and the email registry."""

import time
from datetime import timedelta

import pytest
from django.core import mail
from django.test import Client
from django.utils import timezone

from apps.platform_ops import growth, support_agent
from apps.platform_ops.models import (
    Announcement,
    BillingAuditRun,
    BlogPost,
    EmailTemplate,
    PageSignup,
    PageVisit,
    PlatformKnowledgeDocument,
    PlatformRole,
    PromoCampaign,
    SegmentCategory,
    SignupFunnelEvent,
    SupportTicket,
    UserSegment,
)
from apps.platform_ops.security import new_secret
from apps.tenants.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def console_host(settings):
    settings.ALLOWED_HOSTS = [*settings.ALLOWED_HOSTS, "ops.localhost"]


@pytest.fixture
def operator(user):
    user.is_staff = True
    user.save()
    return PlatformRole.objects.create(
        user=user, role="owner", otp_secret=new_secret(), otp_confirmed=True
    )


def console(operator):
    client = Client(HTTP_HOST="ops.localhost")
    client.force_login(operator.user)
    session = client.session
    session["platform_password_at"] = time.time()
    session["platform_mfa"] = {"version": operator.version, "until": time.time() + 1800}
    session.save()
    return client


def other_user(email="second@example.com"):
    return User.objects.create_user(username=email, email=email, password="A-long-password42")


# ---------------------------------------------------------------- signup funnel


def test_wizard_resumes_at_the_first_unfinished_step(user):
    """Someone who closed the tab mid-wizard comes back where they left off. A wizard
    that restarts at step one would report worse funnel numbers than it deserves."""
    assert growth.wizard_progress(user)["step"] == "connect-instagram"
    growth.record_funnel_event(flow="wizard", step="connect-instagram", status="skipped", user=user)
    growth.record_funnel_event(flow="wizard", step="workspace", status="completed", user=user)
    assert growth.wizard_progress(user)["step"] == "team"
    for step in ["team", "integrations", "payment"]:
        growth.record_funnel_event(flow="wizard", step=step, status="completed", user=user)
    progress = growth.wizard_progress(user)
    assert progress["finished"] and progress["step"] is None


def test_unknown_funnel_steps_are_rejected_not_silently_recorded(user):
    """A renamed step in the frontend must fail loudly here rather than leaving a
    funnel that quietly stops counting."""
    with pytest.raises(ValueError):
        growth.record_funnel_event(flow="wizard", step="not-a-step", status="reached", user=user)
    with pytest.raises(ValueError):
        growth.record_funnel_event(flow="wizard", step="workspace", status="hovered", user=user)
    assert not SignupFunnelEvent.objects.exists()


def test_funnel_counts_distinct_users_and_names_the_worst_drop(user):
    people = [
        user,
        other_user("b@example.com"),
        other_user("c@example.com"),
        other_user("d@example.com"),
    ]
    reach = {
        "connect-instagram": people,
        "workspace": people[:2],
        "team": people[:2],
        "integrations": people[:2],
        "payment": people[:2],
    }
    for step, who in reach.items():
        for person in who:
            growth.record_funnel_event(flow="wizard", step=step, status="reached", user=person)
    # One person refreshing the same step must not look like traffic.
    for _ in range(4):
        growth.record_funnel_event(
            flow="wizard", step="connect-instagram", status="reached", user=user
        )
    report = growth.funnel_report("wizard")
    steps = {row["name"]: row for row in report["steps"]}
    assert steps["connect-instagram"]["reached"] == 4
    assert steps["workspace"]["reached"] == 2
    assert steps["workspace"]["drop_off"] == "50%"
    assert steps["team"]["drop_off"] == "0%"
    assert report["worst"]["name"] == "workspace"


def test_funnel_endpoint_separates_teammates_from_account_owners(client, workspace):
    """A teammate rides the owner's subscription; their tour activity must never be
    counted as a separate signup."""
    from rest_framework.test import APIClient

    from apps.tenants.models import Membership

    teammate = other_user()
    Membership.objects.for_workspace(workspace).create(
        workspace=workspace, user=teammate, role=Membership.Role.AGENT
    )
    body = {
        "flow": "tour",
        "step": "editor",
        "status": "completed",
        "workspace_id": str(workspace.pk),
    }
    assert client.post("/api/growth/funnel/", body, format="json").status_code == 201
    mate = APIClient()
    mate.force_authenticate(teammate)
    assert mate.post("/api/growth/funnel/", body, format="json").status_code == 201
    tour = SignupFunnelEvent.objects.filter(flow="tour")
    assert tour.filter(is_owner=True).count() == 1
    assert tour.filter(is_owner=False).count() == 1

    # Someone with no membership cannot write events against that workspace at all.
    stranger = APIClient()
    stranger.force_authenticate(other_user("stranger@example.com"))
    assert stranger.post("/api/growth/funnel/", body, format="json").status_code == 403


# ------------------------------------------------------------- marketing stats


def test_first_touch_credit_survives_a_later_visit_from_another_source():
    growth.record_page_visit(page="/", session_id="sess-1", referrer="https://instagram.com/x")
    growth.record_page_visit(page="/", session_id="sess-1", referrer="https://google.com/")
    signup = growth.record_page_signup(session_id="sess-1", page="/")
    assert signup.first_touch_source == "instagram.com"
    assert PageVisit.objects.filter(is_first_touch=True).count() == 1


def test_signup_attribution_is_idempotent():
    growth.record_page_visit(page="/", session_id="sess-2")
    growth.record_page_signup(session_id="sess-2", page="/")
    growth.record_page_signup(session_id="sess-2", page="/")
    assert PageSignup.objects.count() == 1


def test_visit_endpoint_is_write_only_and_anonymous(db):
    anonymous = Client()
    assert (
        anonymous.post(
            "/api/growth/visit/",
            {"page": "/pricing", "referrer": "https://news.example/post"},
            content_type="application/json",
        ).status_code
        == 204
    )
    visit = PageVisit.objects.get()
    assert visit.page == "/pricing" and visit.source == "news.example"
    assert anonymous.get("/api/growth/visit/").status_code == 405


def test_signup_records_the_conversion_without_being_able_to_fail_it(db):
    anonymous = Client()
    anonymous.post("/api/growth/visit/", {"page": "/"}, content_type="application/json")
    response = anonymous.post(
        "/api/auth/signup/",
        {
            "name": "Rae",
            "email": "rae@example.com",
            "password": "A-very-long-password42",
            "landing_page": "/",
        },
        content_type="application/json",
    )
    assert response.status_code == 201
    assert PageSignup.objects.filter(user__email="rae@example.com").exists()


# ----------------------------------------------------------------------- blog


def test_blog_beacon_keeps_the_deepest_read_per_session():
    post = BlogPost.objects.create(
        title="Automating first", slug="automating-first", status="published"
    )
    growth.record_blog_view(post=post, session_id="r1", scroll_depth_pct=20, time_spent_seconds=8)
    growth.record_blog_view(post=post, session_id="r1", scroll_depth_pct=95, time_spent_seconds=140)
    # A beacon firing repeatedly during one read is one view, at its furthest point.
    growth.record_blog_view(post=post, session_id="r1", scroll_depth_pct=40, time_spent_seconds=12)
    analytics = growth.blog_analytics()
    assert analytics["views"] == 1
    assert analytics["scroll_depth"] == "95%"
    assert analytics["completion"] == "100%"
    assert analytics["time_spent"] == "140s"


def test_public_blog_serves_published_posts_only(db):
    BlogPost.objects.create(title="Live", slug="live", status="published", body="hello")
    BlogPost.objects.create(title="Draft", slug="draft", status="draft")
    anonymous = Client()
    listing = anonymous.get("/api/blog/").json()
    assert [row["slug"] for row in listing] == ["live"]
    assert anonymous.get("/api/blog/live/").json()["body"] == "hello"
    assert anonymous.get("/api/blog/draft/").status_code == 404


# --------------------------------------------------------------- support flow


def test_ticket_creation_validates_whichever_path_it_comes_from():
    ticket = growth.open_ticket(
        subject="Cannot upgrade", reporter_email="a@example.com", category="billing"
    )
    assert ticket.ticket_number.startswith("#")
    for bad in [
        {"subject": "", "reporter_email": "a@example.com"},
        {"subject": "x", "reporter_email": ""},
        {"subject": "x", "reporter_email": "a@example.com", "category": "invented"},
    ]:
        with pytest.raises(ValueError):
            growth.open_ticket(**bad)
    assert SupportTicket.objects.count() == 1


def test_support_agent_refuses_to_open_a_ticket_without_a_name_and_email():
    """The system prompt says to collect both first, but the prompt is not the
    enforcement — a model can be talked out of an instruction."""
    assert support_agent.create_ticket(name="", email="", subject="Broken") == {
        "ok": False,
        "sentinel": support_agent.NAME_CARD,
    }
    assert support_agent.create_ticket(name="Sam", email="", subject="Broken") == {
        "ok": False,
        "sentinel": support_agent.EMAIL_CARD,
    }
    assert not SupportTicket.objects.exists()
    result = support_agent.create_ticket(
        name="Sam", email="sam@example.com", subject="Broken", category="bug"
    )
    assert result["ok"]
    ticket = SupportTicket.objects.get()
    assert ticket.opened_by_agent and ticket.category == "bug"


def test_support_agent_returns_a_bare_sentinel_never_a_sentinel_plus_prose(db):
    reply = support_agent.answer("I need help", wants_ticket=True)
    assert reply["reply"] == support_agent.NAME_CARD
    assert reply["sentinel"] == support_agent.NAME_CARD


def test_ticket_endpoint_acknowledges_by_email(db):
    response = Client().post(
        "/api/growth/tickets/",
        {"subject": "Billing question", "email": "ask@example.com", "category": "billing"},
        content_type="application/json",
    )
    assert response.status_code == 201
    assert SupportTicket.objects.get().category == "billing"
    assert mail.outbox and "ask@example.com" in mail.outbox[0].to


def test_platform_knowledge_never_reaches_a_tenant_agent(workspace):
    """The two knowledge bases are separate tables on purpose: ours answers our
    prospects, a tenant's answers their leads."""
    from apps.agents.models import KnowledgeDocument

    PlatformKnowledgeDocument.objects.create(title="Competition base")
    KnowledgeDocument.objects.for_workspace(workspace).create(
        workspace=workspace, title="Tenant FAQ", source="secret"
    )
    assert PlatformKnowledgeDocument.objects.count() == 1
    assert not PlatformKnowledgeDocument.objects.filter(title="Tenant FAQ").exists()
    assert not KnowledgeDocument.all_objects.filter(title="Competition base").exists()


# ------------------------------------------------------------ segments + email


def test_classification_reruns_on_reconnect_and_declines_a_thin_bio(workspace, user):
    from apps.channels.models import ChannelConnection
    from apps.platform_ops.tasks import classify_connection

    SegmentCategory.objects.get_or_create(name="Software/SaaS")
    connection = ChannelConnection.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider="instagram",
        external_account_id="ig-1",
        display_name="acme",
        access_token="x",
        expires_at=timezone.now() + timedelta(days=30),
        profile={"biography": "Software/SaaS platform for scheduling."},
    )
    classify_connection(str(connection.pk))
    assert UserSegment.objects.get(user=user).category == "Software/SaaS"

    # A rebranded account must not keep its stale category.
    connection.profile = {"biography": "hi"}
    connection.save(update_fields=["profile"])
    classify_connection(str(connection.pk))
    assert not UserSegment.objects.filter(user=user).exists()


def test_email_registry_renders_placeholders_and_refuses_drafts():
    EmailTemplate.objects.update_or_create(
        name="probe",
        defaults={
            "subject": "Hi {{ name }}",
            "body": "Welcome to {{ workspace }}.",
            "status": "active",
        },
    )
    sent = growth.send_transactional_email("probe", "x@example.com", {"name": "Rae"})
    assert sent["subject"] == "Hi Rae"
    # An unknown placeholder stays visible rather than blanking a value silently.
    assert "{{ workspace }}" in mail.outbox[-1].body

    EmailTemplate.objects.filter(name="probe").update(status="draft")
    with pytest.raises(growth.TemplateMissing):
        growth.send_transactional_email("probe", "x@example.com", {})
    with pytest.raises(growth.TemplateMissing):
        growth.send_transactional_email("no-such-template", "x@example.com", {})


def test_seeded_templates_cover_the_paths_that_send_them():
    for name in ["welcome-v2", "support-ticket-opened", "trial-ending-soon", "plan-changed-v2"]:
        assert EmailTemplate.objects.filter(name=name, status="active").exists(), name


def test_creating_a_workspace_welcomes_the_owner(user):
    from apps.tenants.services import create_workspace

    mail.outbox.clear()
    workspace = create_workspace(user, "Acme")
    assert mail.outbox and workspace.name in mail.outbox[-1].body
    assert SignupFunnelEvent.objects.filter(step="workspace", status="completed").exists()


# ------------------------------------------------------ announcements + promos


def test_popups_show_once_per_viewer_while_strips_repeat(user):
    popup = Announcement.objects.create(type="popup", name="Tour", is_active=True)
    Announcement.objects.create(type="strip", name="Status", is_active=True)
    assert len(growth.announcements_for(user=user)) == 2
    growth.record_announcement_view(popup, user=user)
    remaining = growth.announcements_for(user=user)
    assert [item.type for item in remaining] == ["strip"]


def test_announcement_targeting_scopes_by_page(user):
    Announcement.objects.create(
        type="strip", name="Pricing only", is_active=True, target_pages="pricing, home"
    )
    assert growth.announcements_for(page="pricing", user=user)
    assert not growth.announcements_for(page="inbox", user=user)


def test_campaign_separates_claims_from_redemptions(workspace, user):
    campaign = PromoCampaign.objects.create(slug="annual30", discount_percent=30, is_live=True)
    growth.record_campaign_event(campaign, "shown", workspace=workspace, user=user)
    growth.record_campaign_event(campaign, "claimed", workspace=workspace, user=user)
    totals = growth.campaign_totals(campaign)
    assert totals == {"shown": 1, "claimed": 1, "redeemed": 0}
    with pytest.raises(ValueError):
        growth.record_campaign_event(campaign, "invented")


def test_live_campaign_respects_the_billing_interval(workspace):
    PromoCampaign.objects.create(slug="annual-only", target_interval="annual", is_live=True)
    assert growth.live_campaign_for(workspace, interval="annual")
    assert not growth.live_campaign_for(workspace, interval="monthly")


# --------------------------------------------------------------- console CRUD


def test_console_writes_content_and_audits_every_change(operator):
    client = console(operator)
    assert (
        client.post(
            "/ops/blog/",
            {"title": "Automating first", "status": "published", "body": "text"},
        ).status_code
        == 302
    )
    post = BlogPost.objects.get()
    assert post.slug == "automating-first" and post.published_at

    assert client.post("/ops/segments/", {"name": "Podcasters"}).status_code == 302
    assert SegmentCategory.objects.filter(name="Podcasters").exists()

    assert (
        client.post(
            "/ops/notices/", {"type": "strip", "name": "Status", "tone": "red", "is_active": "on"}
        ).status_code
        == 302
    )
    assert Announcement.objects.get().is_active

    assert (
        client.post(
            "/ops/promos/", {"slug": "launch", "discount_percent": "25", "target_interval": "both"}
        ).status_code
        == 302
    )
    assert PromoCampaign.objects.get().discount_percent == 25

    from apps.platform_ops.models import PlatformAudit

    actions = set(PlatformAudit.objects.values_list("action", flat=True))
    assert {"blog.saved", "segment.category_saved", "announcement.saved", "promo.saved"} <= actions


def test_console_rejects_out_of_range_and_unknown_values(operator):
    client = console(operator)
    assert client.post("/ops/blog/", {"title": "x", "status": "invented"}).status_code == 403
    assert client.post("/ops/blog/", {"title": ""}).status_code == 403
    assert client.post("/ops/promos/", {"slug": "a", "discount_percent": "0"}).status_code == 403
    assert client.post("/ops/notices/", {"type": "banner", "name": "x"}).status_code == 403
    assert not BlogPost.objects.exists() and not PromoCampaign.objects.exists()


def test_ticket_assignment_and_resolution_change_inline(operator):
    ticket = growth.open_ticket(subject="Help", reporter_email="a@example.com")
    client = console(operator)
    response = client.post(
        f"/ops/tickets/{ticket.pk}/",
        {"status": "resolved", "assignee": str(operator.pk), "queue": "support"},
    )
    assert response.status_code == 302
    ticket.refresh_from_db()
    assert ticket.status == "resolved" and ticket.assignee_id == operator.user_id
    assert ticket.is_read


def test_editing_a_section_marks_its_embedding_stale(operator):
    client = console(operator)
    client.post("/ops/knowledge/", {"title": "Support base"})
    document = PlatformKnowledgeDocument.objects.get()
    client.post(
        f"/ops/knowledge/{document.pk}/",
        {"action": "section", "section_title": "Pricing", "body": "Plans cost money."},
    )
    section = document.sections.get()
    section.embedding = [0.0] * 1536
    section.embedded_at = timezone.now()
    section.save()
    client.post(
        f"/ops/knowledge/{document.pk}/",
        {
            "action": "section",
            "section": str(section.pk),
            "section_title": "Pricing",
            "body": "Plans cost rather more money.",
        },
    )
    section.refresh_from_db()
    # Edited content is not retrievable until it is embedded again.
    assert section.embedding is None and section.embedded_at is None


def test_billing_scan_is_on_demand_and_records_its_outcome(operator):
    client = console(operator)
    assert client.post("/ops/billing-scan/").status_code == 302
    run = BillingAuditRun.objects.get()
    # Without Stripe configured the run fails loudly rather than reporting "all clear".
    assert run.status == "failed" and "Stripe" in run.error


def test_console_renders_the_data_it_was_given(operator, workspace, user):
    """Template and context mismatches only surface with rows present, so this walks
    every growth tab with real data in the tables."""
    client = console(operator)
    growth.record_funnel_event(flow="wizard", step="connect-instagram", status="reached", user=user)
    growth.record_page_visit(page="/pricing", session_id="v1", referrer="https://instagram.com/x")
    growth.record_page_signup(session_id="v1", page="/pricing", user=user)
    SegmentCategory.objects.get_or_create(name="Software/SaaS")
    UserSegment.objects.create(
        user=user, category="Software/SaaS", source_account="acme", is_primary=True, confidence=0.9
    )
    post = BlogPost.objects.create(title="Automating first", slug="auto-first", status="published")
    growth.record_blog_view(post=post, session_id="r1", scroll_depth_pct=95, time_spent_seconds=90)
    growth.open_ticket(subject="Cannot upgrade", reporter_email="a@example.com", category="billing")
    Announcement.objects.create(type="strip", name="Status", title="All good", is_active=True)
    PromoCampaign.objects.create(slug="launch", name="Launch", discount_percent=25, is_live=True)
    document = PlatformKnowledgeDocument.objects.create(title="Support base")
    document.sections.create(order=1, title="Pricing", body_markdown="Plans cost money.")

    expected = {
        "funnel": b"connect-instagram",
        "website_stats": b"/pricing",
        "segments": b"Software/SaaS",
        "blog": b"Automating first",
        "support": b"Cannot upgrade",
        "agent_config": b"Support base",
        "promo_offers": b"Launch",
        "notifications": b"All good",
        "email_templates": b"welcome-v2",
        "billing_audit": b"Reconciliation against live Stripe",
    }
    for tab, needle in expected.items():
        response = client.get(f"/ops/?tab={tab}")
        assert response.status_code == 200, tab
        assert needle in response.content, tab
    assert b"Pricing" in client.get(f"/ops/?tab=agent_config&sub={document.pk}").content
    assert b"[[REQUEST_NAME_CARD]]" in client.get("/ops/?tab=agent_config&sub=prompt").content


# ------------------------------------------------------------ console loose ends


def _get(client, url):
    from unittest.mock import patch as _patch

    with _patch("redis.Redis.get", return_value=None), _patch("redis.Redis.ttl", return_value=-2):
        return client.get(url)


def test_editing_a_post_prefills_the_form_so_saving_keeps_the_content(operator):
    post = BlogPost.objects.create(
        title="Keep me", slug="keep-me", status="draft", body="Original body", excerpt="Short"
    )
    body = _get(console(operator), f"/ops/?tab=blog&sub=edit-{post.pk}").content.decode()
    assert 'value="Keep me"' in body and "Original body" in body
    assert f'action="/ops/blog/{post.pk}/"' in body


def test_archive_and_category_rename(operator):
    client = console(operator)
    post = BlogPost.objects.create(title="Old", slug="old", status="published")
    assert client.post(f"/ops/blog/{post.pk}/", {"action": "archive"}).status_code == 302
    post.refresh_from_db()
    assert post.status == "archived"
    assert client.post("/ops/blog/categories/", {"name": "Guides"}).status_code == 302
    category = growth.BlogPost._meta.get_field("category").related_model.objects.get(name="Guides")
    assert (
        client.post(f"/ops/blog/categories/{category.pk}/", {"name": "How-to"}).status_code == 302
    )
    category.refresh_from_db()
    # Renaming keeps the slug, so public category URLs never break.
    assert category.name == "How-to" and category.slug == "guides"
    assert client.post("/ops/blog/categories/", {"name": "How-to"}).status_code == 403


def test_first_touch_toggle_changes_the_source_breakdown(operator):
    growth.record_page_visit(page="/", session_id="s1", referrer="https://instagram.com/")
    growth.record_page_visit(page="/", session_id="s1", referrer="https://google.com/")
    client = console(operator)
    first = _get(client, "/ops/?tab=website_stats&touch=first")
    every = _get(client, "/ops/?tab=website_stats")
    first_sources = [row["name"] for row in first.context["website"]["pages"][0]["sources"]]
    every_sources = [row["name"] for row in every.context["website"]["pages"][0]["sources"]]
    assert first_sources == ["instagram.com"]
    assert set(every_sources) == {"instagram.com", "google.com"}


def test_blog_analytics_window_and_daily_series(operator):
    post = BlogPost.objects.create(title="A", slug="a", status="published")
    growth.record_blog_view(post=post, session_id="x", scroll_depth_pct=50)
    week = _get(console(operator), "/ops/?tab=blog&sub=analytics&days=7")
    analytics = week.context["blog"]["analytics"]
    assert analytics["days"] == 7 and len(analytics["daily"]) == 7
    assert analytics["daily"][-1]["total"] == 1


def test_editing_an_announcement_prefills_it(operator):
    item = Announcement.objects.create(
        type="popup", name="Launch", title="We shipped", tone="green", target_pages="home"
    )
    body = _get(console(operator), f"/ops/?tab=notifications&edit={item.pk}").content.decode()
    assert 'value="Launch"' in body and 'value="We shipped"' in body and 'value="home"' in body
    assert f'action="/ops/notices/{item.pk}/"' in body
    assert 'value="green" selected' in body


def test_support_staff_reply_is_visible_to_reporter(
    operator, workspace, django_capture_on_commit_callbacks
):
    from rest_framework.test import APIClient

    from apps.platform_ops.models import SupportTicketMessage

    ticket = growth.open_ticket(
        subject="Cannot publish", reporter_email=operator.user.email, workspace=workspace
    )
    ticket.reporter = operator.user
    ticket.save()
    with django_capture_on_commit_callbacks(execute=True):
        response = console(operator).post(
            f"/ops/tickets/{ticket.pk}/",
            {"reply": "Please reconnect your channel.", "queue": "support"},
        )
    assert response.status_code == 302
    assert SupportTicketMessage.objects.get(ticket=ticket).from_staff
    assert mail.outbox[-1].to == [operator.user.email]
    client = APIClient()
    client.force_authenticate(operator.user)
    rows = client.get(f"/api/workspaces/{workspace.pk}/support/tickets/").json()
    assert rows[0]["messages"][0]["body"] == "Please reconnect your channel."

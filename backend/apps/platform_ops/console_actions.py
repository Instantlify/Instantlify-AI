"""Mutating console endpoints for the growth sections.

Every view here is `@protected(...)`, POST-only, and writes an audit row: the console
is the one place where a person can change Nemio's own content and billing state, so
nothing may change without a name attached to it.
"""

from django.db import IntegrityError, transaction
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from .growth import send_transactional_email
from .models import (
    Announcement,
    BillingAuditRun,
    BlogCategory,
    BlogPost,
    EmailTemplate,
    PlatformKnowledgeDocument,
    PlatformKnowledgeSection,
    PlatformSetting,
    PromoCampaign,
    SegmentCategory,
    SupportTicket,
)
from .security import record
from .views import protected

TRUE = {"on", "true", "1", "yes"}


def flag(data, name):
    return str(data.get(name, "")).lower() in TRUE


def whole(data, name, default=0):
    value = str(data.get(name, "")).strip()
    try:
        return int(value) if value else default
    except ValueError:
        raise Http404 from None


# ---------------------------------------------------------------------- blog


@require_POST
@protected("owner", "support")
@transaction.atomic
def blog_save(request, pk=None):
    data = request.POST
    if data.get("action") == "delete":
        post = get_object_or_404(BlogPost, pk=pk)
        record(request.user, "blog.deleted", slug=post.slug)
        post.delete()
        return redirect("/ops/?tab=blog")
    if data.get("action") == "archive":
        post = get_object_or_404(BlogPost.objects.select_for_update(), pk=pk)
        post.status = "archived"
        post.save(update_fields=["status", "updated_at"])
        record(request.user, "blog.archived", slug=post.slug)
        return redirect("/ops/?tab=blog")
    title = data.get("title", "").strip()[:200]
    if not title:
        return HttpResponseForbidden("A post needs a title.")
    slug = slugify(data.get("slug") or title)[:220]
    status = data.get("status", "draft")
    if status not in BlogPost.STATUSES:
        return HttpResponseForbidden("Unknown post status.")
    category = None
    if data.get("category"):
        category, _ = BlogCategory.objects.get_or_create(
            name=data["category"].strip()[:80],
            defaults={"slug": slugify(data["category"])[:90]},
        )
    fields = {
        "title": title,
        "category": category,
        "status": status,
        "excerpt": data.get("excerpt", "").strip()[:300],
        "body": data.get("body", ""),
        "thumbnail_url": data.get("thumbnail_url", "").strip()[:2000],
    }
    # Publishing stamps a date once; re-saving a published post must not move it.
    if status == "published":
        fields["published_at"] = (
            BlogPost.objects.filter(pk=pk).values_list("published_at", flat=True).first()
            or timezone.now()
        )
    try:
        if pk:
            post = get_object_or_404(BlogPost.objects.select_for_update(), pk=pk)
            for key, value in {**fields, "slug": slug}.items():
                setattr(post, key, value)
            post.save()
        else:
            post = BlogPost.objects.create(slug=slug, **fields)
    except IntegrityError:
        return HttpResponseForbidden("That slug is already taken.")
    record(request.user, "blog.saved", slug=post.slug, status=post.status)
    return redirect("/ops/?tab=blog")


@require_POST
@protected("owner", "support")
def blog_category_save(request, pk=None):
    """Create a category, or rename one. Renaming keeps the slug stable so public
    category URLs do not break."""
    name = request.POST.get("name", "").strip()[:80]
    if not name:
        return HttpResponseForbidden("A category needs a name.")
    try:
        if pk:
            category = get_object_or_404(BlogCategory, pk=pk)
            category.name = name
            category.save(update_fields=["name"])
        else:
            category = BlogCategory.objects.create(name=name, slug=slugify(name)[:90])
    except IntegrityError:
        return HttpResponseForbidden("A category with that name already exists.")
    record(request.user, "blog.category_saved", name=category.name)
    return redirect("/ops/?tab=blog&sub=categories")


# -------------------------------------------------------------------- tickets


@require_POST
@protected("owner", "support")
@transaction.atomic
def ticket_update(request, pk):
    """Assignee and resolution change inline from the list. Both are routine ops
    actions; forcing a detail-page round trip for them would be friction for nothing."""
    ticket = get_object_or_404(SupportTicket.objects.select_for_update(), pk=pk)
    changes = {}
    if "status" in request.POST:
        status = request.POST["status"]
        if status not in {"unresolved", "resolved"}:
            return HttpResponseForbidden("Unknown ticket status.")
        ticket.status = status
        changes["status"] = status
    if "assignee" in request.POST:
        from .models import PlatformRole

        value = request.POST["assignee"]
        if value:
            role = get_object_or_404(PlatformRole.objects.select_related("user"), pk=value)
            ticket.assignee = role.user
            changes["assignee"] = role.user.get_username()
        else:
            ticket.assignee = None
            changes["assignee"] = "unassigned"
    ticket.is_read = True
    ticket.save()
    record(request.user, "ticket.updated", target=ticket.ticket_number, **changes)
    return redirect(f"/ops/?tab=support&sub={request.POST.get('queue', '')}")


# ------------------------------------------------------------- knowledge base


@require_POST
@protected("owner")
@transaction.atomic
def knowledge_save(request, pk=None):
    data = request.POST
    action = data.get("action")
    if action == "reembed":
        from .tasks import embed_platform_knowledge

        embed_platform_knowledge.delay()
        record(request.user, "knowledge.reembed_requested")
        return redirect("/ops/?tab=agent_config")
    if action == "delete_section":
        section = get_object_or_404(PlatformKnowledgeSection, pk=data.get("section"))
        record(request.user, "knowledge.section_deleted", target=str(section.pk))
        section.delete()
        return redirect(f"/ops/?tab=agent_config&sub={section.document_id}")
    if action == "prompt":
        PlatformSetting.objects.update_or_create(
            key="support_agent_system_prompt", defaults={"value": data.get("prompt", "")[:20000]}
        )
        record(request.user, "knowledge.prompt_saved")
        return redirect("/ops/?tab=agent_config&sub=prompt")
    if pk:
        document = get_object_or_404(PlatformKnowledgeDocument.objects.select_for_update(), pk=pk)
    else:
        title = data.get("title", "").strip()[:200]
        if not title:
            return HttpResponseForbidden("A document needs a title.")
        document = PlatformKnowledgeDocument.objects.create(
            title=title, tag=data.get("tag", "").strip()[:40]
        )
        record(request.user, "knowledge.document_created", target=str(document.pk))
        return redirect(f"/ops/?tab=agent_config&sub={document.pk}")
    if action == "section":
        title = data.get("section_title", "").strip()[:200]
        if not title:
            return HttpResponseForbidden("A section needs a title.")
        level = whole(data, "heading_level", 2)
        section_id = data.get("section")
        if section_id:
            section = get_object_or_404(
                PlatformKnowledgeSection.objects.select_for_update(),
                pk=section_id,
                document=document,
            )
            section.title = title
            section.heading_level = min(3, max(1, level))
            section.body_markdown = data.get("body", "")
            # Edited content invalidates its embedding; it is stale until re-embedded.
            section.embedding = None
            section.embedded_at = None
            section.save()
        else:
            last = document.sections.order_by("-order").values_list("order", flat=True).first()
            PlatformKnowledgeSection.objects.create(
                document=document,
                order=(last or 0) + 1,
                heading_level=min(3, max(1, level)),
                title=title,
                body_markdown=data.get("body", ""),
            )
        record(request.user, "knowledge.section_saved", target=str(document.pk))
        return redirect(f"/ops/?tab=agent_config&sub={document.pk}")
    document.title = data.get("title", document.title).strip()[:200]
    document.tag = data.get("tag", document.tag).strip()[:40]
    document.description = data.get("description", "").strip()[:300]
    document.save()
    record(request.user, "knowledge.document_saved", target=str(document.pk))
    return redirect(f"/ops/?tab=agent_config&sub={document.pk}")


# --------------------------------------------------------------------- promos


@require_POST
@protected("owner")
@transaction.atomic
def promo_save(request, pk=None):
    """Campaigns are live config: launching or changing one takes effect immediately
    and must never need a deploy."""
    from apps.billing.models import Plan

    data = request.POST
    if data.get("action") == "delete":
        campaign = get_object_or_404(PromoCampaign, pk=pk)
        record(request.user, "promo.deleted", slug=campaign.slug)
        campaign.delete()
        return redirect("/ops/?tab=promo_offers")
    interval = data.get("target_interval", "both")
    if interval not in PromoCampaign.INTERVALS:
        return HttpResponseForbidden("Unknown billing interval.")
    percent = whole(data, "discount_percent", 10)
    if not 1 <= percent <= 100:
        return HttpResponseForbidden("A discount must be between 1 and 100 percent.")
    fields = {
        "name": data.get("name", "").strip()[:100],
        "discount_percent": percent,
        "target_interval": interval,
        "is_live": flag(data, "is_live"),
    }
    if pk:
        campaign = get_object_or_404(PromoCampaign.objects.select_for_update(), pk=pk)
        for key, value in fields.items():
            setattr(campaign, key, value)
        campaign.save()
    else:
        slug = slugify(data.get("slug") or fields["name"])[:60]
        if not slug or PromoCampaign.objects.filter(slug=slug).exists():
            return HttpResponseForbidden("Choose a unique campaign slug.")
        campaign = PromoCampaign.objects.create(slug=slug, **fields)
    campaign.target_plans.set(Plan.objects.filter(slug__in=data.getlist("plans")))
    record(request.user, "promo.saved", slug=campaign.slug, live=campaign.is_live)
    return redirect("/ops/?tab=promo_offers")


# -------------------------------------------------------------- announcements


@require_POST
@protected("owner", "support")
@transaction.atomic
def announcement_save(request, pk=None):
    from apps.billing.models import Plan

    data = request.POST
    if data.get("action") == "delete":
        item = get_object_or_404(Announcement, pk=pk)
        record(request.user, "announcement.deleted", target=item.name)
        item.delete()
        return redirect("/ops/?tab=notifications")
    kind = data.get("type", "strip")
    if kind not in Announcement.TYPES:
        return HttpResponseForbidden("Unknown announcement type.")
    tone = data.get("tone", "dark")
    if tone not in Announcement.TONES:
        return HttpResponseForbidden("Unknown tone.")
    fields = {
        "type": kind,
        "name": data.get("name", "").strip()[:100] or "Untitled",
        "title": data.get("title", "").strip()[:200],
        "body": data.get("body", ""),
        "tone": tone,
        "link_url": data.get("link_url", "").strip()[:2000],
        "target_pages": data.get("target_pages", "").strip()[:500],
        "is_active": flag(data, "is_active"),
    }
    if pk:
        item = get_object_or_404(Announcement.objects.select_for_update(), pk=pk)
        for key, value in fields.items():
            setattr(item, key, value)
        item.save()
    else:
        item = Announcement.objects.create(**fields)
    item.target_plans.set(Plan.objects.filter(slug__in=data.getlist("plans")))
    record(request.user, "announcement.saved", target=item.name, active=item.is_active)
    return redirect("/ops/?tab=notifications")


# ------------------------------------------------------------ email templates


@require_POST
@protected("owner")
@transaction.atomic
def email_template_save(request, pk=None):
    """Copy is content, not code. A draft row is edited freely but `send_transactional_email`
    refuses to send it, so an unfinished rewrite cannot reach a customer."""
    data = request.POST
    if data.get("action") == "test":
        template = get_object_or_404(EmailTemplate, pk=pk)
        target = data.get("to", "").strip()
        if not target:
            return HttpResponseForbidden("Enter an address to send the test to.")
        try:
            send_transactional_email(template.name, target, {})
        except Exception as exc:  # noqa: BLE001 - surfaced to the operator verbatim
            return HttpResponseForbidden(f"Test send failed: {exc}")
        record(request.user, "email_template.tested", name=template.name)
        return redirect("/ops/?tab=email_templates&saved=1")
    status = data.get("status", "draft")
    if status not in {"active", "draft"}:
        return HttpResponseForbidden("Unknown template status.")
    subject = data.get("subject", "").strip()[:300]
    if not subject:
        return HttpResponseForbidden("A template needs a subject.")
    fields = {
        "description": data.get("description", "").strip()[:300],
        "subject": subject,
        "body": data.get("body", ""),
        "status": status,
    }
    if pk:
        template = get_object_or_404(EmailTemplate.objects.select_for_update(), pk=pk)
        for key, value in fields.items():
            setattr(template, key, value)
        template.save()
    else:
        name = slugify(data.get("name", ""))[:80]
        if not name or EmailTemplate.objects.filter(name=name).exists():
            return HttpResponseForbidden("Choose a unique template name.")
        template = EmailTemplate.objects.create(name=name, **fields)
    record(request.user, "email_template.saved", name=template.name, status=template.status)
    return redirect("/ops/?tab=email_templates&saved=1")


# ------------------------------------------------------------------- segments


@require_POST
@protected("owner", "support")
def segment_category_save(request):
    """The classifier reads its label set from the database, so a new category takes
    effect on the next run without a redeploy."""
    name = request.POST.get("name", "").strip()[:80]
    if not name:
        return HttpResponseForbidden("A category needs a name.")
    SegmentCategory.objects.update_or_create(
        name=name, defaults={"description": request.POST.get("description", "").strip()[:300]}
    )
    record(request.user, "segment.category_saved", name=name)
    return redirect("/ops/?tab=segments")


# -------------------------------------------------------------- billing audit


@require_POST
@protected("owner")
def billing_scan(request):
    """On-demand only. This spends real Stripe calls, so it runs when a person asks
    and never on a timer."""
    from .tasks import scan_billing

    run = BillingAuditRun.objects.create()
    scan_billing.delay(run.pk)
    record(request.user, "billing.scan_started", target=str(run.pk))
    return redirect("/ops/?tab=billing_audit")


# ---------------------------------------------------------------------- users


def _target_user(pk):
    from apps.tenants.models import User

    return get_object_or_404(User, pk=pk)


@require_POST
@protected("owner", "support")
def user_ban(request, pk):
    """Ban cascades: sign-in blocked, sessions and refresh tokens dead, every owned
    workspace paused. An analyst role cannot reach this at all."""
    from . import accounts

    user = _target_user(pk)
    if user.pk == request.user.pk:
        return HttpResponseForbidden("You cannot ban your own account.")
    try:
        accounts.ban_user(user, operator=request.user, reason=request.POST.get("reason", ""))
    except ValueError as exc:
        return HttpResponseForbidden(str(exc))
    return redirect(f"/ops/?tab=users&q={user.email}")


@require_POST
@protected("owner", "support")
def user_unban(request, pk):
    from . import accounts

    user = _target_user(pk)
    accounts.unban_user(user, operator=request.user, reason=request.POST.get("reason", ""))
    return redirect(f"/ops/?tab=users&q={user.email}")


@require_POST
@protected("owner", "support")
def user_email(request, pk):
    """Operator email goes to the configured outbound webhook, never to an SMTP server
    hard-coded here, so the sending infrastructure stays swappable."""
    from apps.channels.transport import ProviderError
    from apps.channels.transport import request as outbound

    from .growth import email_hook_payload, outbound_email_hook

    user = _target_user(pk)
    subject = request.POST.get("subject", "").strip()[:200]
    message = request.POST.get("message", "").strip()[:10000]
    if not subject or not message:
        return HttpResponseForbidden("An email needs a subject and a message.")
    url = outbound_email_hook()
    if not url:
        return HttpResponseForbidden(
            "No email automation link is configured. Set one under Settings first."
        )
    payload = email_hook_payload(
        operator=request.user, target_user=user, subject=subject, message=message
    )
    try:
        outbound("POST", url, json=payload, side_effect=True)
    except ProviderError as exc:
        record(request.user, "user.email_failed", target=str(user.pk), code=exc.code)
        return HttpResponseForbidden(f"The email endpoint did not accept the message ({exc.code}).")
    record(request.user, "user.emailed", target=str(user.pk), subject=subject)
    return redirect(f"/ops/?tab=users&q={user.email}&sent=1")


@require_POST
@protected("owner", "support")
def user_create(request):
    from django.core.exceptions import ValidationError

    from . import accounts

    try:
        user = accounts.create_user(
            name=request.POST.get("name", ""),
            email=request.POST.get("email", ""),
            password=request.POST.get("password", ""),
            workspace_name=request.POST.get("workspace", "").strip(),
            operator=request.user,
        )
    except ValidationError as exc:
        return HttpResponseForbidden(" ".join(exc.messages))
    except ValueError as exc:
        return HttpResponseForbidden(str(exc))
    return redirect(f"/ops/?tab=users&q={user.email}")


# ----------------------------------------------------------------- AI credits


@require_POST
@protected("owner")
def provider_test(request):
    """One real, minimal paid call against one key, on demand only. Throttled to one
    test per key per minute so a double-click cannot become a bill."""
    from django.core.cache import cache

    from .intelligence import KEY_PATTERN, ping

    env = request.POST.get("env", "")
    if not KEY_PATTERN.match(env):
        return HttpResponseForbidden("Unknown provider key.")
    if not cache.add(f"ops:provider-throttle:{env}", 1, 60):
        return HttpResponseForbidden("That key was tested less than a minute ago.")
    result = {**ping(env), "at": timezone.now()}
    cache.set(f"ops:provider-test:{env}", result, 60 * 60 * 24)
    record(request.user, "provider.tested", key=env, ok=result["ok"], error=result["error"])
    return redirect("/ops/?tab=ai_credits")


RATE_FIELDS = [
    f"{side}_{field}"
    for side in ["our", "real"]
    for field in ["input", "output", "cache_read", "cache_write"]
]


def dollars_to_cents(value):
    """The rate card is typed in dollars per million tokens and stored in cents."""
    from decimal import Decimal, InvalidOperation

    text = str(value or "").strip().lstrip("$")
    if not text:
        return Decimal(0)
    try:
        amount = Decimal(text)
    except InvalidOperation:
        raise ValueError("Rates must be numbers.") from None
    if amount < 0:
        raise ValueError("Rates cannot be negative.")
    return (amount * 100).quantize(Decimal("0.0001"))


@require_POST
@protected("owner")
@transaction.atomic
def rate_save(request, pk=None):
    """Create, edit or delete a rate card. The fallback row can be edited but never
    deleted: an unrecognised model must always have something to bill against."""
    from apps.billing.models import ModelPricingRate

    data = request.POST
    if data.get("action") == "delete":
        rate = get_object_or_404(ModelPricingRate, pk=pk)
        if rate.is_fallback_default:
            return HttpResponseForbidden("The fallback rate cannot be deleted.")
        record(request.user, "rate.deleted", pattern=rate.model_pattern)
        rate.delete()
        return redirect("/ops/?tab=ai_credits&sub=pricing")
    try:
        values = {field: dollars_to_cents(data.get(field)) for field in RATE_FIELDS}
    except ValueError as exc:
        return HttpResponseForbidden(str(exc))
    if pk:
        rate = get_object_or_404(ModelPricingRate.objects.select_for_update(), pk=pk)
    else:
        pattern = data.get("model_pattern", "").strip()[:100]
        if not pattern or pattern == "%":
            return HttpResponseForbidden("Enter a model pattern, e.g. claude-opus%.")
        if ModelPricingRate.objects.filter(model_pattern=pattern).exists():
            return HttpResponseForbidden("That pattern already has a rate card.")
        rate = ModelPricingRate(model_pattern=pattern)
    rate.label = data.get("label", rate.label).strip()[:100]
    for field, value in values.items():
        setattr(rate, field, value)
    rate.save()
    record(
        request.user,
        "rate.saved",
        pattern=rate.model_pattern,
        **{field: str(value) for field, value in values.items()},
    )
    return redirect("/ops/?tab=ai_credits&sub=pricing")


# ---------------------------------------------------------------- automations


def _automation_and_target(request, pk):
    from apps.automations.models import Automation
    from apps.channels.models import ChannelConnection

    automation = get_object_or_404(Automation.all_objects.select_related("workspace"), pk=pk)
    connection = get_object_or_404(
        ChannelConnection.all_objects.select_related("workspace"),
        pk=request.POST.get("target", ""),
    )
    return automation, connection


@require_POST
@protected("owner", "support")
def automation_copy(request, pk):
    from django.core.exceptions import ValidationError as DjangoValidationError
    from rest_framework.exceptions import ValidationError

    from apps.automations.services import duplicate

    automation, connection = _automation_and_target(request, pk)
    try:
        copy = duplicate(automation, connection.workspace, request.user)
    except (ValidationError, DjangoValidationError, ValueError) as exc:
        return HttpResponseForbidden(f"Copy failed: {exc}")
    record(
        request.user,
        "automation.copied",
        connection.workspace_id,
        source=str(automation.pk),
        copy=str(copy.pk),
        from_workspace=str(automation.workspace_id),
    )
    return redirect(f"/ops/?tab=automations&sub={connection.pk}")


@require_POST
@protected("owner", "support")
def automation_transfer(request, pk):
    from apps.automations.services import transfer

    automation, connection = _automation_and_target(request, pk)
    source = automation.workspace_id
    try:
        transfer(
            automation,
            connection.workspace,
            operator=request.user,
            reason=request.POST.get("reason", ""),
        )
    except ValueError as exc:
        return HttpResponseForbidden(str(exc))
    record(
        request.user,
        "automation.transferred",
        connection.workspace_id,
        automation=str(automation.pk),
        from_workspace=str(source),
        reason=request.POST.get("reason", "")[:300],
    )
    return redirect(f"/ops/?tab=automations&sub={connection.pk}")


@require_POST
@protected("owner", "support")
def user_portal_link(request, pk):
    """Email a Stripe billing-portal link. The session is created now, at send time:
    it is single-use and expires within minutes, so it is never made ahead or stored."""
    import stripe

    from apps.billing.emails import owners, send_manage_link
    from apps.billing.models import BillingAccount

    from . import accounts

    user = _target_user(pk)
    owned = accounts.owned_workspace_ids(user)
    account = (
        BillingAccount.all_objects.filter(workspace_id__in=owned).exclude(customer_id=None).first()
    )
    if not account:
        return HttpResponseForbidden("This user owns no workspace with a Stripe customer.")
    membership = next((m for m in owners(account.workspace_id) if m.user_id == user.pk), None)
    try:
        sent = send_manage_link(account, membership)
    except (ValueError, stripe.StripeError) as exc:
        return HttpResponseForbidden(f"Could not create a portal link: {exc}")
    record(request.user, "user.portal_link_sent", account.workspace_id, target=str(user.pk))
    return redirect(f"/ops/?tab=users&q={user.email}&sent={1 if sent else 0}")

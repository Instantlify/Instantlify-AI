"""Endpoints the tenant app and the public marketing site call into.

These write platform-owned rows (funnel steps, page visits, tickets, announcement
reads) from outside the console. Everything here is either anonymous-and-write-only
or scoped to the caller's own account — none of it can read another account's data,
and none of it exposes the console's aggregates.
"""

from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from . import growth
from .models import Announcement, BlogPost, PromoCampaign, SignupFunnelEvent


class PublicWrite(APIView):
    """Anonymous, write-only tracking. Returns nothing readable on purpose: these
    endpoints are open to the internet and must not become a data source."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AnonRateThrottle]


# ------------------------------------------------------------------ signup funnel


class FunnelEventView(APIView):
    """The wizard and the product tour report their own step transitions here.

    Attribution goes to the real account behind the action: a teammate riding an
    owner's subscription is flagged `is_owner=False` so their tour activity is never
    counted as a separate signup.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]

    def post(self, request):
        from apps.tenants.models import Membership, Workspace

        workspace = None
        is_owner = True
        workspace_id = request.data.get("workspace_id")
        if workspace_id:
            membership = Membership.all_objects.filter(
                user=request.user, workspace_id=workspace_id
            ).first()
            if not membership:
                return Response({"detail": "Not a member of this workspace."}, status=403)
            workspace = Workspace.objects.filter(pk=workspace_id).first()
            is_owner = membership.role == "owner"
        try:
            growth.record_funnel_event(
                flow=request.data.get("flow", "wizard"),
                step=request.data.get("step", ""),
                status=request.data.get("status", ""),
                user=request.user,
                workspace=workspace,
                is_owner=is_owner,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"recorded": True}, status=201)


class WizardProgressView(APIView):
    """Where to resume someone who closed the tab mid-wizard."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        progress = growth.wizard_progress(request.user)
        return Response({**progress, "steps": SignupFunnelEvent.WIZARD_STEPS})


# --------------------------------------------------------------- marketing site


class PageVisitView(PublicWrite):
    def post(self, request):
        page = str(request.data.get("page", "/"))[:200]
        growth.record_page_visit(
            page=page,
            session_id=growth.session_key(request),
            source=str(request.data.get("source", ""))[:120],
            referrer=str(request.data.get("referrer", ""))[:500],
        )
        return Response(status=204)


class BlogViewBeaconView(PublicWrite):
    """Scroll depth and dwell time — the two things a plain page-view counter cannot
    tell you, and the reason this beacon exists separately from PageVisit."""

    def post(self, request):
        post = BlogPost.objects.filter(
            slug=str(request.data.get("slug", ""))[:220], status="published"
        ).first()
        if not post:
            return Response(status=204)

        def whole(name):
            try:
                return max(0, int(request.data.get(name, 0)))
            except (TypeError, ValueError):
                return 0

        growth.record_blog_view(
            post=post,
            session_id=growth.session_key(request),
            scroll_depth_pct=whole("scroll_depth_pct"),
            time_spent_seconds=whole("time_spent_seconds"),
        )
        return Response(status=204)


class PublicBlogList(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AnonRateThrottle]

    def get(self, request):
        return Response(
            [
                {
                    "title": post.title,
                    "slug": post.slug,
                    "excerpt": post.excerpt,
                    "category": post.category.name if post.category else "",
                    "thumbnail_url": post.thumbnail_url,
                    "published_at": post.published_at,
                }
                for post in growth.published_posts()[:50]
            ]
        )


class PublicBlogDetail(PublicBlogList):
    def get(self, request, slug):
        post = get_object_or_404(growth.published_posts(), slug=slug)
        return Response(
            {
                "title": post.title,
                "slug": post.slug,
                "excerpt": post.excerpt,
                "body": post.body,
                "category": post.category.name if post.category else "",
                "thumbnail_url": post.thumbnail_url,
                "published_at": post.published_at,
            }
        )


# -------------------------------------------------------------------- support


class PublicTicketInput(serializers.Serializer):
    subject = serializers.CharField(max_length=200)
    email = serializers.EmailField()
    name = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    body = serializers.CharField(max_length=10000, required=False, allow_blank=True, default="")
    category = serializers.ChoiceField(choices=["billing", "bug", "support"], default="support")
    channel = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")


class SupportTicketView(APIView):
    """A person filing a ticket from the app. The platform support agent files
    through the same service function, so neither path can skip validation."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        user = request.user if request.user.is_authenticated else None
        fields = PublicTicketInput(
            data={**request.data, "email": request.data.get("email") or getattr(user, "email", "")}
        )
        fields.is_valid(raise_exception=True)
        data = fields.validated_data
        try:
            ticket = growth.open_ticket(
                subject=data["subject"],
                body=data["body"],
                category=data["category"],
                reporter_email=data["email"],
                reporter_name=data["name"] or getattr(user, "first_name", ""),
                reporter_channel=data["channel"],
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        try:
            growth.send_transactional_email(
                "support-ticket-opened",
                ticket.reporter_email,
                {
                    "name": ticket.reporter_name or "there",
                    "ticket_number": ticket.ticket_number,
                    "subject": ticket.subject,
                },
            )
        except (growth.TemplateMissing, OSError):
            # A failed acknowledgement must never lose the ticket itself.
            pass
        return Response({"ticket_number": ticket.ticket_number}, status=201)


class SupportChatView(PublicWrite):
    """One turn with Instantlify's own support assistant.

    The reply may be a sentinel token (`[[REQUEST_NAME_CARD]]` / `[[REQUEST_EMAIL_CARD]]`)
    rather than prose: the client renders those as a real input field, which beats
    asking in prose and hoping the answer comes back parseable.
    """

    def post(self, request):
        from . import support_agent

        name = str(request.data.get("name", ""))[:120]
        email = str(request.data.get("email", ""))[:254]
        if request.data.get("create_ticket"):
            try:
                result = support_agent.create_ticket(
                    name=name,
                    email=email,
                    subject=str(request.data.get("subject", ""))[:200] or "Support request",
                    body=str(request.data.get("body", ""))[:4000],
                    category=str(request.data.get("category", "support")),
                )
            except ValueError as exc:
                return Response({"detail": str(exc)}, status=400)
            return Response(result, status=201 if result.get("ok") else 200)
        from apps.channels.transport import ProviderError

        try:
            result = support_agent.answer(
                str(request.data.get("message", ""))[:2000],
                name=name,
                email=email,
                wants_ticket=bool(request.data.get("wants_ticket")),
            )
        except ProviderError:
            result = {
                "reply": "The assistant is temporarily unavailable. Please use Raise a ticket and our team will help.",
                "sentinel": None,
                "sources": [],
            }
        return Response(result)


# -------------------------------------------------------- announcements + promos


class AnnouncementListView(APIView):
    """Active announcements for this viewer, on this page. Strips repeat; popups are
    filtered out once this user has seen them."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .notifications import safe_link, viewer_plan

        plan = viewer_plan(request)
        rows = growth.announcements_for(
            page=request.query_params.get("page", ""), plan=plan, user=request.user
        )
        return Response(
            [
                {
                    "id": item.pk,
                    "type": item.type,
                    "name": item.name,
                    "title": item.title,
                    "body": item.body,
                    "tone": item.tone,
                    "link_url": safe_link(item.link_url),
                    "revision": item.revision,
                    "requires_acknowledgement": item.requires_acknowledgement,
                }
                for item in rows
            ]
        )


class AnnouncementSeenView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        from .notifications import eligible_notices, viewer_plan

        eligible = [
            item.pk
            for item in eligible_notices(
                page=request.query_params.get("page", ""), plan=viewer_plan(request)
            )
        ]
        announcement = get_object_or_404(Announcement, pk=pk, pk__in=eligible)
        growth.record_announcement_view(announcement, user=request.user)
        return Response(status=204)


class PromoView(APIView):
    """The live campaign this workspace qualifies for, if any. Fetching it counts as
    `shown`; activating it is a separate `claimed` call, and the discount actually
    landing on a Stripe subscription is `redeemed` — three different numbers."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.billing.services import account_for
        from apps.tenants.models import Membership

        workspace_id = request.query_params.get("workspace_id")
        membership = Membership.all_objects.filter(
            user=request.user, workspace_id=workspace_id
        ).first()
        if not membership:
            return Response({"campaign": None})
        price = getattr(account_for(workspace_id), "plan_price", None)
        campaign = growth.live_campaign_for(
            membership.workspace,
            interval=getattr(price, "billing_interval", None),
            plan=getattr(price, "plan", None),
        )
        if not campaign:
            return Response({"campaign": None})
        growth.record_campaign_event(
            campaign, "shown", workspace=membership.workspace, user=request.user
        )
        return Response(
            {
                "campaign": {
                    "slug": campaign.slug,
                    "name": campaign.name or campaign.slug,
                    "discount_percent": campaign.discount_percent,
                    "target_interval": campaign.target_interval,
                }
            }
        )

    def post(self, request):
        from apps.tenants.models import Membership

        membership = Membership.all_objects.filter(
            user=request.user, workspace_id=request.data.get("workspace_id")
        ).first()
        if not membership:
            return Response({"detail": "Not a member of this workspace."}, status=403)
        campaign = get_object_or_404(PromoCampaign, slug=request.data.get("slug", ""), is_live=True)
        growth.record_campaign_event(
            campaign, "claimed", workspace=membership.workspace, user=request.user
        )
        return Response({"claimed": True}, status=201)


def campaign_rows():
    """Campaigns with their shown/claimed/redeemed counts, for the console."""
    rows = []
    for campaign in PromoCampaign.objects.prefetch_related("target_plans").annotate(
        event_total=Count("events")
    ):
        counts = growth.campaign_totals(campaign)
        plans = list(campaign.target_plans.all())
        rows.append(
            {
                "campaign": campaign,
                "targets": ", ".join(plan.name for plan in plans) or "all paid tiers",
                "shown": counts["shown"],
                "claimed": counts["claimed"],
                "redeemed": counts["redeemed"],
            }
        )
    return rows

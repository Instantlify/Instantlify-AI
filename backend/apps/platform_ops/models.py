import uuid

from django.conf import settings
from django.db import models
from pgvector.django import VectorField

from apps.tenants.crypto import EncryptedTextField


class CommunityPost(models.Model):
    """Intentionally shared with all authenticated members, independent of tenants."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    body = EncryptedTextField()
    pinned = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-pinned", "-created_at", "-id"]


class CommunityReply(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    post = models.ForeignKey(CommunityPost, related_name="replies", on_delete=models.CASCADE)
    parent = models.ForeignKey(
        "self", null=True, blank=True, related_name="children", on_delete=models.SET_NULL
    )
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    body = EncryptedTextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class CommunityVote(models.Model):
    post = models.ForeignKey(CommunityPost, related_name="votes", on_delete=models.CASCADE)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    value = models.SmallIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["post", "author"], name="one_community_vote"),
            models.CheckConstraint(
                condition=models.Q(value__in=[-1, 1]), name="valid_community_vote"
            ),
        ]


class AffiliateAccount(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    promoter_id = models.PositiveBigIntegerField(null=True, unique=True)
    status = models.CharField(max_length=20, default="new")
    last_error = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class PlatformRole(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    role = models.CharField(
        max_length=20,
        choices=[("owner", "Owner"), ("support", "Support"), ("analyst", "Read-only analyst")],
    )
    active = models.BooleanField(default=True)
    otp_secret = EncryptedTextField(blank=True)
    otp_confirmed = models.BooleanField(default=False)
    last_counter = models.BigIntegerField(default=-1)
    failed_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True)
    version = models.PositiveIntegerField(default=1)


class Control(models.Model):
    # An empty scope means platform-wide; otherwise an exact workspace UUID.
    scope = models.CharField(max_length=36, blank=True)
    key = models.CharField(max_length=100)
    disabled = models.BooleanField(default=True)
    reason = models.CharField(max_length=300)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["scope", "key"], name="unique_platform_control")
        ]


class WorkspaceCapability(models.Model):
    workspace = models.ForeignKey("tenants.Workspace", on_delete=models.CASCADE)
    key = models.CharField(max_length=100)
    enabled = models.BooleanField(default=False)
    reason = models.CharField(max_length=300)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workspace", "key"], name="unique_workspace_capability")
        ]


class PlatformAudit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor_id = models.CharField(max_length=36)
    action = models.CharField(max_length=80)
    workspace_id = models.CharField(max_length=36, blank=True)
    detail = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Platform audit entries are immutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Platform audit entries are immutable")


class SupportSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    operator = models.ForeignKey(PlatformRole, on_delete=models.PROTECT)
    workspace = models.ForeignKey("tenants.Workspace", on_delete=models.CASCADE)
    reason = models.CharField(max_length=300)
    expires_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True)


class PlatformInvite(models.Model):
    email = models.EmailField()
    role = models.CharField(max_length=20)
    digest = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True)


class OperationStatus(models.Model):
    provider = models.CharField(max_length=30, unique=True)
    review_status = models.CharField(max_length=100, default="Not verified")
    permissions = models.CharField(max_length=1000, blank=True)
    certificate_expires_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class DailyMetric(models.Model):
    day = models.DateField()
    name = models.CharField(max_length=80)
    value = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["day", "name"], name="unique_ops_daily_metric")
        ]


class SubscriptionSnapshot(models.Model):
    workspace = models.ForeignKey("tenants.Workspace", on_delete=models.CASCADE)
    day = models.DateField()
    currency = models.CharField(max_length=3)
    monthly_cents = models.DecimalField(max_digits=18, decimal_places=4)
    status = models.CharField(max_length=30)
    overage = models.PositiveIntegerField(default=0)
    synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "day", "currency"], name="unique_subscription_snapshot"
            )
        ]


class PlatformSetting(models.Model):
    """Small key/value store for console-managed platform settings, so an operator can
    change an endpoint or toggle without a deploy. Values are plain text; nothing secret
    belongs here."""

    key = models.CharField(max_length=80, unique=True)
    value = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key"]

    @classmethod
    def get(cls, key, default=""):
        row = cls.objects.filter(key=key).first()
        return row.value if row else default


# ======================================================================== growth
# Platform-owned tables behind the admin console. These describe Instantlify's own
# business (who signed up, what the marketing site does, who filed a ticket) and
# are deliberately not tenant-scoped: nothing here is a `TenantModel`, and no
# tenant API reads any of it.


class SignupFunnelEvent(models.Model):
    """One row per step transition in the signup wizard and the post-signup product
    tour. Funnels count distinct users per step, so a re-rendered step writing a
    second `reached` row is harmless."""

    WIZARD_STEPS = ["connect-instagram", "workspace", "team", "integrations", "payment"]
    TOUR_STEPS = ["editor", "crm", "apps", "claude-mcp"]
    STATUSES = ["reached", "completed", "skipped"]

    flow = models.CharField(max_length=10, default="wizard")
    step = models.CharField(max_length=40)
    status = models.CharField(max_length=10)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    workspace = models.ForeignKey("tenants.Workspace", null=True, on_delete=models.SET_NULL)
    # A teammate riding an owner's subscription is never a separate signup.
    is_owner = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["flow", "step", "status"])]


class PageVisit(models.Model):
    """First-party marketing-site analytics. Separate from product analytics on
    purpose: this tracks logged-out visitors on public pages."""

    page = models.CharField(max_length=200)
    source = models.CharField(max_length=120, blank=True)
    session_id = models.CharField(max_length=64)
    referrer = models.CharField(max_length=500, blank=True)
    # The source credited with the session that first brought this visitor in.
    is_first_touch = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["page", "created_at"]),
            models.Index(fields=["session_id"]),
        ]


class PageSignup(models.Model):
    """Links a completed signup back to the visit session that produced it, so a
    landing page's conversion is measurable end to end."""

    page = models.CharField(max_length=200)
    source = models.CharField(max_length=120, blank=True)
    first_touch_source = models.CharField(max_length=120, blank=True)
    session_id = models.CharField(max_length=64)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["session_id"], name="one_signup_per_session")
        ]


class SegmentCategory(models.Model):
    """The classifier's label set, editable without a redeploy."""

    name = models.CharField(max_length=80, unique=True)
    description = models.CharField(max_length=300, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "segment categories"


class UserSegment(models.Model):
    """A marketing category inferred from one connected account's bio, name and
    linked site. Re-derived whenever that account reconnects, since a bio changes.
    A user holds one row per (account, category): an agency managing several client
    accounts is how a user ends up spanning categories."""

    UNCLASSIFIED = "insufficient_evidence"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    workspace = models.ForeignKey("tenants.Workspace", null=True, on_delete=models.SET_NULL)
    connection_id = models.UUIDField(null=True)
    source_account = models.CharField(max_length=200, blank=True)
    category = models.CharField(max_length=80)
    confidence = models.FloatField(default=0)
    # The account the user signed up with; category counts use primaries only.
    is_primary = models.BooleanField(default=False)
    evidence = models.CharField(max_length=500, blank=True)
    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user_id", "category"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "source_account", "category"], name="one_segment_per_account"
            )
        ]
        indexes = [models.Index(fields=["category"])]


class BlogCategory(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=90, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "blog categories"


class BlogPost(models.Model):
    STATUSES = ["draft", "published", "archived"]

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    category = models.ForeignKey(BlogCategory, null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=10, default="draft")
    excerpt = models.CharField(max_length=300, blank=True)
    body = models.TextField(blank=True)
    thumbnail_url = models.URLField(max_length=2000, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-published_at", "-created_at", "-id"]


class BlogPostView(models.Model):
    """Beacon rows from public blog pages. Scroll depth and dwell time are what a
    plain page-view counter cannot tell you, and they are the whole point here."""

    post = models.ForeignKey(BlogPost, on_delete=models.CASCADE)
    session_id = models.CharField(max_length=64)
    scroll_depth_pct = models.PositiveSmallIntegerField(default=0)
    time_spent_seconds = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["post", "session_id"], name="one_view_per_session")
        ]


class SupportTicket(models.Model):
    """Filed by a person through the support form, or by the platform support agent
    through its `create_ticket` tool. Both paths land here with the same validation."""

    CATEGORIES = ["billing", "support", "bug"]

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="support_tickets",
    )
    ticket_number = models.CharField(max_length=20, unique=True)
    category = models.CharField(max_length=10, default="support")
    subject = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    reporter_name = models.CharField(max_length=120, blank=True)
    reporter_email = models.EmailField()
    reporter_channel = models.CharField(max_length=30, blank=True)
    workspace = models.ForeignKey("tenants.Workspace", null=True, on_delete=models.SET_NULL)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    status = models.CharField(max_length=12, default="unresolved")
    is_read = models.BooleanField(default=False)
    opened_by_agent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["category", "status"])]


class SupportTicketMessage(models.Model):
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    from_staff = models.BooleanField(default=False)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class PlatformKnowledgeDocument(models.Model):
    """Instantlify's OWN support bot knowledge base. Deliberately a separate table from
    `agents.KnowledgeDocument`: that one holds a tenant's content and answers a
    tenant's leads. These must never retrieve into each other's context."""

    title = models.CharField(max_length=200)
    tag = models.CharField(max_length=40, blank=True)
    description = models.CharField(max_length=300, blank=True)
    embedded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["title"]


class PlatformKnowledgeSection(models.Model):
    document = models.ForeignKey(
        PlatformKnowledgeDocument, related_name="sections", on_delete=models.CASCADE
    )
    order = models.PositiveIntegerField(default=0)
    heading_level = models.PositiveSmallIntegerField(default=2)
    title = models.CharField(max_length=200)
    body_markdown = models.TextField(blank=True)
    embedding = VectorField(dimensions=1536, null=True, blank=True)
    embedded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["document_id", "order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["document", "order"], name="one_section_per_position")
        ]


class PromoCampaign(models.Model):
    """In-app discount campaigns. Every parameter is live config; launching or
    changing one must never need a deploy."""

    INTERVALS = ["monthly", "annual", "both"]

    slug = models.SlugField(max_length=60, unique=True)
    name = models.CharField(max_length=100, blank=True)
    discount_percent = models.PositiveSmallIntegerField(default=10)
    target_interval = models.CharField(max_length=10, default="both")
    target_plans = models.ManyToManyField("billing.Plan", blank=True)
    is_live = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def targets_all_paid_plans(self):
        return not self.target_plans.exists()


class PromoCampaignEvent(models.Model):
    """`claimed` is the user activating the offer; `redeemed` is the discount
    actually landing on a Stripe subscription. The gap between them is the point."""

    EVENTS = ["shown", "claimed", "redeemed"]

    campaign = models.ForeignKey(PromoCampaign, related_name="events", on_delete=models.CASCADE)
    workspace = models.ForeignKey("tenants.Workspace", null=True, on_delete=models.SET_NULL)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    event_type = models.CharField(max_length=10)
    # The Stripe subscription a redemption landed on; makes a replayed webhook a no-op.
    reference = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["campaign", "event_type"])]
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "event_type", "reference"],
                condition=~models.Q(reference=""),
                name="one_campaign_event_per_reference",
            )
        ]


class Announcement(models.Model):
    """Popups (modal, once per viewer) and strips (persistent banner) are one CMS,
    not two systems: they differ only in how the client renders them."""

    TYPES = ["popup", "strip"]
    TONES = ["dark", "blue", "green", "orange", "red", "plain"]

    type = models.CharField(max_length=6, default="strip")
    name = models.CharField(max_length=100)
    title = models.CharField(max_length=200, blank=True)
    body = models.TextField(blank=True)
    tone = models.CharField(max_length=10, default="dark")
    link_url = models.URLField(max_length=2000, blank=True)
    # Empty on either dimension means "everywhere" / "every tier".
    target_pages = models.CharField(max_length=500, blank=True)
    target_plans = models.ManyToManyField("billing.Plan", blank=True)
    is_active = models.BooleanField(default=False)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    schedule_timezone = models.CharField(max_length=64, default="Asia/Karachi")
    requires_acknowledgement = models.BooleanField(default=False)
    revision = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def pages(self):
        return [page.strip() for page in self.target_pages.split(",") if page.strip()]


class AnnouncementView(models.Model):
    announcement = models.ForeignKey(Announcement, related_name="views", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    session_id = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["announcement", "user"],
                condition=models.Q(user__isnull=False),
                name="one_announcement_view_per_user",
            )
        ]


class AnnouncementNotification(models.Model):
    """Delivered snapshots survive expiry, edits and removal of their source notice."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    announcement = models.ForeignKey(
        Announcement, null=True, on_delete=models.SET_NULL, related_name="notifications"
    )
    revision = models.PositiveIntegerField(default=1)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    link_url = models.URLField(max_length=2000, blank=True)
    tone = models.CharField(max_length=10, default="dark")
    requires_acknowledgement = models.BooleanField(default=False)
    expires_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-delivered_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "announcement", "revision"], name="one_notice_delivery_per_revision"
            )
        ]
        indexes = [models.Index(fields=["user", "read_at"], name="notice_user_read_idx")]


class EmailTemplate(models.Model):
    """Every transactional email's copy, keyed by a stable name. `send_transactional_email`
    looks a row up by that name at send time, so changing wording is a content edit
    and never a deploy. A `draft` row is edited but never sent."""

    name = models.SlugField(max_length=80, unique=True)
    description = models.CharField(max_length=300, blank=True)
    subject = models.CharField(max_length=300)
    body = models.TextField(blank=True)
    status = models.CharField(max_length=6, default="draft")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]


class BillingAuditRun(models.Model):
    """One on-demand reconciliation of the local subscription state against live
    Stripe. Never scheduled: it costs real API calls and is a human's question."""

    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True)
    status = models.CharField(max_length=12, default="running")
    checked = models.PositiveIntegerField(default=0)
    findings = models.JSONField(default=dict)
    error = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-started_at", "-id"]

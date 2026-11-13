from django.db import models

from apps.tenants.crypto import EncryptedTextField
from apps.tenants.models import TenantModel


class DeepLink(TenantModel):
    """A short public link (/go/<code>/) that opens the native app for the target."""

    title = models.CharField(max_length=80)
    # instagram, whatsapp, youtube, telegram or custom; only affects the UI.
    platform = models.CharField(max_length=20, default="custom")
    open_external = models.BooleanField(default=False)
    target = models.URLField(max_length=2000)
    code = models.SlugField(max_length=40, unique=True)
    clicks = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)
    campaign = models.CharField(max_length=100, blank=True)
    source = models.CharField(max_length=100, blank=True)
    medium = models.CharField(max_length=100, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class LinkClickDay(TenantModel):
    link = models.ForeignKey(DeepLink, on_delete=models.CASCADE)
    day = models.DateField()
    clicks = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["link", "day"], name="one_link_click_day")]


class LeadForm(TenantModel):
    title = models.CharField(max_length=120)
    slug = models.SlugField(max_length=80, unique=True)
    description = models.CharField(max_length=1000, blank=True)
    fields = models.JSONField(default=list)
    submission_actions = models.JSONField(default=list)
    automation_id = models.UUIDField(null=True, blank=True)
    branching = models.JSONField(default=list)
    theme = models.JSONField(default=dict)
    redirect_url = models.URLField(max_length=2000, blank=True)
    submission_tags = models.JSONField(default=list)
    button_align = models.CharField(max_length=6, default="left")
    closed = models.BooleanField(default=False)
    capture_contacts = models.BooleanField(default=True)
    consent_text = models.CharField(
        max_length=500, default="I agree to be contacted about my enquiry."
    )
    success_text = models.CharField(
        max_length=500, default="Thank you. Your response has been received."
    )
    published = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class FormSubmission(TenantModel):
    action_errors = models.JSONField(default=list)
    workflow_state = EncryptedTextField(default="{}")
    workflow_status = models.CharField(max_length=20, blank=True)
    workflow_due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    form = models.ForeignKey(LeadForm, on_delete=models.CASCADE)
    lead = models.ForeignKey("crm.Lead", null=True, on_delete=models.SET_NULL)
    link = models.ForeignKey(DeepLink, null=True, on_delete=models.SET_NULL)
    request_id = models.UUIDField()
    answers = EncryptedTextField()
    consent_text = models.CharField(max_length=500)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["form", "request_id"], name="unique_form_submission")
        ]
        ordering = ["-created_at", "-id"]


class CreatorKit(TenantModel):
    slug = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=120)
    headline = models.CharField(max_length=200, blank=True)
    bio = models.CharField(max_length=2000, blank=True)
    contact_email = models.EmailField(blank=True)
    links = models.JSONField(default=list)
    statistics = models.JSONField(default=list)
    live_connection_ids = models.JSONField(default=list)
    live_insights = models.BooleanField(default=False)
    live_stats_next_at = models.DateTimeField(null=True, blank=True, db_index=True)
    live_stats_checked_at = models.DateTimeField(null=True, blank=True)
    live_stats_started_at = models.DateTimeField(null=True, blank=True)
    live_stats_token = models.UUIDField(null=True, blank=True)
    live_stats_error = models.CharField(max_length=50, blank=True)
    services = models.JSONField(default=list)
    published = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["workspace"], name="one_creator_kit")]


class ShieldRule(TenantModel):
    """Comments containing any of `keywords` (or, for an AI rule, matching the plain
    language `prompt`) are hidden, deleted or flagged, optionally with a public reply."""

    name = models.CharField(max_length=80)
    keywords = models.JSONField(default=list)
    # AI rule: what to catch, e.g. "insults, harassment or spam links". Blank = keyword rule.
    prompt = models.CharField(max_length=500, blank=True)
    # Posted publicly under the comment when the rule matches (not with "delete").
    reply_text = models.CharField(max_length=300, blank=True)
    action = models.CharField(max_length=10, default="hide")
    enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]


class ShieldEvent(TenantModel):
    """One comment a rule matched and what happened to it."""

    rule = models.ForeignKey(ShieldRule, null=True, on_delete=models.SET_NULL)
    rule_name = models.CharField(max_length=80)
    connection = models.ForeignKey("channels.ChannelConnection", on_delete=models.CASCADE)
    comment_id = models.CharField(max_length=255)
    author = models.CharField(max_length=150)
    text = models.TextField(max_length=2000)
    # hidden, deleted, flagged, or failed when the provider refused the action.
    action_taken = models.CharField(max_length=20)

    class Meta:
        ordering = ["-created_at", "-id"]


class WebChatSettings(TenantModel):
    """Appearance and access rules of the workspace's website chat widget."""

    title = models.CharField(max_length=80, default="Chat with us")
    greeting = models.CharField(max_length=500, default="Hi there! How can we help you today?")
    color = models.CharField(max_length=7, default="#347359")
    bot_enabled = models.BooleanField(default=True)
    position = models.CharField(max_length=5, default="right")
    launcher_label = models.CharField(max_length=20, default="Chat")
    logo_url = models.URLField(max_length=2000, blank=True)
    # Suggested first messages shown as buttons under the greeting.
    quick_replies = models.JSONField(default=list, blank=True)
    # Hostnames allowed to embed the widget; empty allows any site.
    allowed_domains = models.JSONField(default=list)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["workspace"], name="one_webchat_settings")]

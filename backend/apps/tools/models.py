from django.db import models

from apps.tenants.models import TenantModel


class DeepLink(TenantModel):
    """A short public link (/go/<code>/) that opens the native app for the target."""

    title = models.CharField(max_length=80)
    # instagram, whatsapp, youtube, telegram or custom; only affects the UI.
    platform = models.CharField(max_length=20, default="custom")
    target = models.URLField(max_length=2000)
    code = models.SlugField(max_length=40, unique=True)
    clicks = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class ShieldRule(TenantModel):
    """Comments containing any of `keywords` are hidden, deleted or flagged."""

    name = models.CharField(max_length=80)
    keywords = models.JSONField(default=list)
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
    # Hostnames allowed to embed the widget; empty allows any site.
    allowed_domains = models.JSONField(default=list)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["workspace"], name="one_webchat_settings")]

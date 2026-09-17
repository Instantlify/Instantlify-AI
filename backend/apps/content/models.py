from django.db import models

from apps.tenants.models import TenantModel


class ScheduledPost(TenantModel):
    """A creator's own feed post, published by Beat at `scheduled_at`.

    Separate from the automation engine: this is outbound content, not a reply."""

    connection = models.ForeignKey("channels.ChannelConnection", on_delete=models.CASCADE)
    caption = models.TextField(max_length=2200, blank=True)
    media_url = models.URLField(max_length=2000)
    media_type = models.CharField(max_length=10, default="image")
    scheduled_at = models.DateTimeField()
    # scheduled → publishing (container created, processing) → published | failed | unknown
    status = models.CharField(max_length=20, default="scheduled")
    attempts = models.PositiveIntegerField(default=0)
    # Instagram media container: recorded before any publish call so a lost worker can
    # resume polling instead of creating a second container or publishing twice.
    container_id = models.CharField(max_length=120, blank=True)
    container_created_at = models.DateTimeField(null=True)
    polls = models.PositiveIntegerField(default=0)
    provider_post_id = models.CharField(max_length=120, blank=True)
    error_code = models.CharField(max_length=50, blank=True)
    published_at = models.DateTimeField(null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["scheduled_at", "id"]
        indexes = [models.Index(fields=["status", "scheduled_at"])]


class BioPage(TenantModel):
    """Public, workspace-branded link page served at /p/<slug>/."""

    slug = models.SlugField(max_length=60, unique=True)
    title = models.CharField(max_length=80)
    bio = models.CharField(max_length=300, blank=True)
    avatar_url = models.URLField(max_length=2000, blank=True)
    accent = models.CharField(max_length=7, default="#347359")
    # [{"title": str, "url": https}] — at most 20, validated at the API boundary.
    links = models.JSONField(default=list)
    published = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["workspace"], name="one_bio_page")]

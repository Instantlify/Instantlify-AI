from django.db import models

from apps.tenants.models import TenantModel


class Template(TenantModel):
    """A published automation graph other workspaces can install.

    The owning workspace is the author. Graphs are re-validated on install, so a
    template can never put an unpublishable flow into another tenant."""

    title = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.TextField(blank=True, max_length=2000)
    category = models.CharField(max_length=40, default="sales")
    graph = models.JSONField()
    author_name = models.CharField(max_length=100, blank=True)
    price_cents = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, default="published")
    install_count = models.PositiveIntegerField(default=0)
    source_automation_id = models.UUIDField(null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-install_count", "-created_at"]
        indexes = [models.Index(fields=["status", "category"])]


class TemplateInstall(TenantModel):
    """Installer-side record; `template_id` is a plain UUID because it crosses tenants."""

    template_id = models.UUIDField()
    automation = models.ForeignKey("automations.Automation", on_delete=models.CASCADE)

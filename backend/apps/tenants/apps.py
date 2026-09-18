from django.apps import AppConfig
from django.db.models.signals import post_migrate


class TenantsConfig(AppConfig):
    name = "apps.tenants"
    label = "tenants"

    def ready(self):
        from .isolation import on_post_migrate

        post_migrate.connect(on_post_migrate, dispatch_uid="nemio_tenant_isolation")

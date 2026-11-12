from django.apps import AppConfig
from django.db.models.signals import post_migrate


class TenantsConfig(AppConfig):
    name = "apps.tenants"
    label = "tenants"

    def ready(self):
        from django.contrib.auth.signals import user_logged_in

        from .isolation import on_post_migrate
        from .sessions import on_login

        post_migrate.connect(on_post_migrate, dispatch_uid="nemio_tenant_isolation")
        user_logged_in.connect(on_login, dispatch_uid="instantlify_session_activity")

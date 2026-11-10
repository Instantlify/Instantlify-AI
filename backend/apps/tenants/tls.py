import logging

from django.conf import settings
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from .models import WorkspaceBranding

log = logging.getLogger(__name__)


def is_domain_allowed_for_tls(domain: str) -> bool:
    """Checks whether on-demand TLS certificate issuance is authorized for `domain`."""
    if not domain:
        return False
    domain = domain.strip().lower().split(":")[0]

    # Standard platform domains are always allowed
    platform_hosts = {
        "instantlify.com",
        "app.nemio.ai",
        "ops.nemio.ai",
        "ops.localhost",
        getattr(settings, "APP_DOMAIN", "instantlify.com").lower(),
        getattr(settings, "PLATFORM_ADMIN_HOST", "ops.localhost").lower(),
        "localhost",
        "127.0.0.1",
    }
    if domain in platform_hosts:
        return True

    # Active verified custom domains
    return WorkspaceBranding.all_objects.filter(
        custom_domain=domain,
        custom_domain_status=WorkspaceBranding.DomainStatus.ACTIVE,
    ).exists()


class CheckDomainTLSView(APIView):
    """Internal authorization endpoint queried by Caddy's on_demand_tls.

    Caddy passes the domain to authorize via the `domain` query param:
    `GET /api/v1/tls/check-domain/?domain=client.agency.com`

    Returns HTTP 200 if certificate issuance is authorized; HTTP 404 if denied.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AnonRateThrottle]

    def get(self, request):
        domain = request.query_params.get("domain") or request.headers.get("X-Forwarded-Host") or ""
        domain = domain.strip().lower().split(":")[0]

        if not domain:
            return Response({"error": "domain_required", "allowed": False}, status=400)

        if is_domain_allowed_for_tls(domain):
            return Response({"domain": domain, "allowed": True}, status=200)

        log.info("Caddy TLS on-demand check rejected unauthorized domain: %s", domain)
        return Response(
            {"domain": domain, "allowed": False, "error": "unauthorized_domain"}, status=404
        )

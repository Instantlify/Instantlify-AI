import ipaddress

from django.conf import settings
from django.http import HttpResponse


class ConsoleBoundary:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        console = request.path.startswith("/ops/")
        host = request.get_host().split(":")[0].lower()
        dedicated = host == settings.PLATFORM_ADMIN_HOST
        if console and not dedicated:
            return HttpResponse(status=404)
        if dedicated and not console and request.path not in {"/health/live/", "/health/ready/"}:
            return HttpResponse(status=404)
        if console and settings.PLATFORM_ADMIN_NETWORKS:
            try:
                ip = ipaddress.ip_address(request.META.get("REMOTE_ADDR", ""))
                allowed = any(
                    ip in ipaddress.ip_network(net) for net in settings.PLATFORM_ADMIN_NETWORKS
                )
            except ValueError:
                allowed = False
            if not allowed:
                return HttpResponse(status=403)
        response = self.get_response(request)
        if (
            request.path in {"/webhooks/instagram/", "/webhooks/whatsapp/", "/webhooks/messenger/"}
            and request.method == "POST"
        ):
            from .metrics import increment

            result = (
                "accepted"
                if response.status_code == 200
                else "signature_rejected"
                if response.status_code == 403
                else "failed"
            )
            increment("webhook." + result)
        if console:
            response["Cache-Control"] = "private, no-store"
            # "no-referrer" makes browsers send "Origin: null" on same-origin form posts,
            # which Django's CSRF origin check rejects. same-origin still leaks nothing
            # cross-site while letting the console's own forms submit.
            response["Referrer-Policy"] = "same-origin"
            response["Content-Security-Policy"] = (
                "default-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; form-action 'self'"
            )
        return response

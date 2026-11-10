""" "Test connection" for saved integrations.

Each supported provider gets one lightweight, read-only authenticated request (no
messages sent, no records written). The result says whether the provider accepted the
saved credentials; secrets and provider response bodies never leave the server.
"""

import json
from urllib.parse import quote

from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.channels.transport import ProviderError, RetryableError, request
from apps.tenants.permissions import workspace_membership
from apps.tenants.services import audit

from .models import IntegrationConfig


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def probe(provider, credentials, options):
    """(method, url, kwargs) for the provider's identity check, or None if unsupported."""
    token = credentials.get("api_key") or credentials.get("access_token") or ""
    if provider == "slack":
        return "POST", "https://slack.com/api/auth.test", {"headers": _bearer(token)}
    if provider == "airtable":
        return "GET", "https://api.airtable.com/v0/meta/whoami", {"headers": _bearer(token)}
    if provider == "notion":
        return (
            "GET",
            "https://api.notion.com/v1/users/me",
            {"headers": {**_bearer(token), "Notion-Version": "2022-06-28"}},
        )
    if provider == "mailerlite":
        return (
            "GET",
            "https://connect.mailerlite.com/api/subscribers?limit=1",
            {"headers": _bearer(token)},
        )
    if provider == "klaviyo":
        return (
            "GET",
            "https://a.klaviyo.com/api/accounts/",
            {"headers": {"Authorization": f"Klaviyo-API-Key {token}", "revision": "2024-10-15"}},
        )
    if provider == "stripe":
        secret = credentials.get("secret_key", "")
        return "GET", "https://api.stripe.com/v1/balance", {"headers": _bearer(secret)}
    if provider == "elevenlabs":
        return "GET", "https://api.elevenlabs.io/v1/user", {"headers": {"xi-api-key": token}}
    if provider == "heygen":
        return (
            "GET",
            "https://api.heygen.com/v2/user/remaining_quota",
            {"headers": {"x-api-key": token}},
        )
    if provider == "vapi":
        return "GET", "https://api.vapi.ai/assistant?limit=1", {"headers": _bearer(token)}
    if provider == "retell":
        return "GET", "https://api.retellai.com/list-agents", {"headers": _bearer(token)}
    if provider == "calcom":
        return "GET", "https://api.cal.com/v2/me", {"headers": _bearer(token)}
    if provider == "attio":
        return "GET", "https://api.attio.com/v2/self", {"headers": _bearer(token)}
    if provider == "gohighlevel" and options.get("location_id"):
        return (
            "GET",
            "https://services.leadconnectorhq.com/locations/"
            + quote(str(options["location_id"]), safe=""),
            {"headers": {**_bearer(token), "Version": "2021-07-28"}},
        )
    return None


def run_test(config):
    if config.is_test or settings.CHANNEL_ADAPTER_MODE == "fake":
        return {"ok": True, "detail": "Test mode: no provider was contacted."}
    from .integrations import credentials_for

    try:
        credentials = credentials_for(config)
    except ProviderError as exc:
        return {"ok": False, "detail": _explain(exc.code)}
    options = json.loads(config.options) if isinstance(config.options, str) else config.options
    check = probe(config.provider, credentials, options or {})
    if check is None:
        return {
            "ok": None,
            "detail": "This provider has no connection test yet; run the step once to check it.",
        }
    method, url, kwargs = check
    try:
        body = request(method, url, **kwargs)
    except RetryableError:
        return {"ok": False, "detail": "The provider did not respond. Try again shortly."}
    except ProviderError as exc:
        return {"ok": False, "detail": _explain(exc.code)}
    if config.provider == "slack" and isinstance(body, dict) and body.get("ok") is False:
        return {"ok": False, "detail": "Slack rejected the token."}
    return {"ok": True, "detail": "Connected: the provider accepted these credentials."}


def _explain(code):
    return {
        "invalid_api_key": "The provider rejected this API key.",
        "integration_reconnect_required": "Reconnect this account; its sign-in has expired.",
        "integration_oauth_not_configured": "Google sign-in is not configured on this server.",
    }.get(code, "The provider rejected these credentials or settings.")


class IntegrationTestView(APIView):
    def post(self, request, workspace_id, pk):
        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        config = get_object_or_404(IntegrationConfig.objects.for_workspace(workspace_id), pk=pk)
        result = run_test(config)
        audit(
            member.workspace,
            request.user,
            "integration.tested",
            config.pk,
            provider=config.provider,
        )
        return Response(result)

import hashlib
import secrets

from django.utils import timezone
from rest_framework import authentication, exceptions, permissions, throttling

from .models import APIKey

PREFIX = "nmk_"


def generate_key():
    raw = PREFIX + secrets.token_urlsafe(32)
    return raw, raw[: len(PREFIX) + 8], hashlib.sha256(raw.encode()).hexdigest()


class APIKeyPrincipal:
    """Non-user principal so DRF's IsAuthenticated semantics hold for key callers."""

    is_authenticated = True
    is_active = True
    is_anonymous = False
    is_staff = False
    pk = None
    id = None

    def __init__(self, key):
        self.api_key = key
        self.workspace_id = key.workspace_id

    def __str__(self):
        return f"api-key:{self.api_key.prefix}"


class APIKeyAuthentication(authentication.BaseAuthentication):
    """`X-API-Key: nmk_…` — separate header from JWT so the two cannot be confused."""

    def authenticate(self, request):
        raw = request.headers.get("X-API-Key", "")
        if not raw:
            return None
        if not raw.startswith(PREFIX) or len(raw) > 120:
            raise exceptions.AuthenticationFailed("Invalid API key.")
        key = (
            APIKey.all_objects.filter(
                key_hash=hashlib.sha256(raw.encode()).hexdigest(), revoked_at__isnull=True
            )
            .select_related("workspace")
            .first()
        )
        if not key:
            raise exceptions.AuthenticationFailed("Invalid API key.")
        APIKey.all_objects.filter(pk=key.pk).update(last_used_at=timezone.now())
        return APIKeyPrincipal(key), key

    def authenticate_header(self, request):
        return "X-API-Key"


class HasAPIKey(permissions.BasePermission):
    def has_permission(self, request, view):
        principal = getattr(request, "user", None)
        if not isinstance(principal, APIKeyPrincipal):
            return False
        needed = "read" if request.method in permissions.SAFE_METHODS else "write"
        return needed in principal.api_key.scopes


class APIKeyThrottle(throttling.SimpleRateThrottle):
    scope = "api_key"

    def get_cache_key(self, request, view):
        principal = getattr(request, "user", None)
        if not isinstance(principal, APIKeyPrincipal):
            return None
        return f"throttle_api_key_{principal.api_key.pk}"

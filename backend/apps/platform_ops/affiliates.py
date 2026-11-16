"""Owner-bound FirstPromoter access. No provider creation happens during GET."""

from decimal import Decimal
from urllib.parse import urlsplit

from django.conf import settings
from django.db import IntegrityError, transaction
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.channels.transport import ProviderError
from apps.channels.transport import request as provider_request

from .models import AffiliateAccount

BASE = "https://api.firstpromoter.com/api/v2/company/promoters"


def configured():
    return bool(settings.FIRSTPROMOTER_API_KEY and settings.FIRSTPROMOTER_ACCOUNT_ID)


def headers():
    return {
        "Account-ID": settings.FIRSTPROMOTER_ACCOUNT_ID,
        "Authorization": f"Bearer {settings.FIRSTPROMOTER_API_KEY}",
    }


def customer_id(user):
    return f"instantlify:{user.pk}"


def owned(data, user):
    return isinstance(data, dict) and data.get("cust_id") == customer_id(user)


def find_promoter(user):
    body = provider_request(
        "GET", BASE, headers=headers(), params={"q": user.email, "per_page": 100}
    )
    rows = body.get("data") if isinstance(body, dict) else body
    if not isinstance(rows, list):
        raise ProviderError("affiliate_response_invalid")
    matches = [item for item in rows if owned(item, user)]
    if len(matches) > 1:
        raise ProviderError("affiliate_identity_conflict")
    if matches:
        return matches[0]
    if any(
        isinstance(item, dict) and str(item.get("email", "")).lower() == user.email.lower()
        for item in rows
    ):
        raise ProviderError("affiliate_identity_conflict")
    return None


def safe_link(value):
    if not isinstance(value, str) or len(value) > 2000 or any(ord(char) < 33 for char in value):
        return ""
    try:
        parsed = urlsplit(value)
        if parsed.port not in {None, 443}:
            return ""
        return (
            value
            if parsed.scheme == "https"
            and parsed.hostname
            and not parsed.username
            and not parsed.password
            else ""
        )
    except ValueError:
        return ""


def positive_number(value):
    return value if type(value) is int and value >= 0 else 0


def public_data(data):
    stats = data.get("stats") if isinstance(data.get("stats"), dict) else {}
    revenue = stats.get("revenue_amount", 0)
    try:
        divisor = Decimal(str(settings.FIRSTPROMOTER_REVENUE_DIVISOR))
        if not divisor.is_finite() or divisor <= 0:
            raise ValueError("Invalid revenue divisor")
        amount = Decimal(str(revenue)) / divisor
        revenue_text = str(amount.quantize(Decimal("0.01"))) if amount.is_finite() else None
    except (ValueError, ArithmeticError):
        revenue_text = None
    campaigns = []
    raw_campaigns = data.get("promoter_campaigns")
    if not isinstance(raw_campaigns, list):
        raw_campaigns = []
    for row in raw_campaigns[:100]:
        if not isinstance(row, dict):
            continue
        campaign = row.get("campaign") if isinstance(row.get("campaign"), dict) else {}
        campaigns.append(
            {
                "name": str(campaign.get("name") or "Referral campaign")[:200],
                "state": str(row.get("state") or "pending")[:30],
                "ref_link": safe_link(row.get("ref_link")),
                "coupon": str(row.get("coupon") or "")[:200],
            }
        )
    return {
        "stats": {
            key: positive_number(stats.get(key))
            for key in (
                "clicks_count",
                "referrals_count",
                "sales_count",
                "customers_count",
                "active_customers_count",
            )
        },
        "revenue": revenue_text,
        "currency": settings.FIRSTPROMOTER_CURRENCY,
        "campaigns": campaigns,
        "joined_at": data.get("joined_at"),
        "is_confirmed": data.get("is_confirmed") is True,
    }


def save_binding(account, data, user):
    if not owned(data, user) or type(data.get("id")) is not int or data["id"] < 1:
        raise ProviderError("affiliate_identity_conflict")
    account.promoter_id, account.status, account.last_error = data["id"], "active", ""
    try:
        with transaction.atomic():
            account.save(update_fields=["promoter_id", "status", "last_error", "updated_at"])
    except IntegrityError:
        raise ProviderError("affiliate_identity_conflict") from None


class AffiliateThrottle(UserRateThrottle):
    scope = "affiliate"
    rate = "15/min"


class AffiliateView(APIView):
    throttle_classes = [AffiliateThrottle]

    def get(self, request):
        if not configured():
            return Response({"configured": False, "status": "unavailable"})
        if not request.user.email_verified_at:
            return Response({"configured": True, "status": "verify_email"})
        account = AffiliateAccount.objects.filter(user=request.user).first()
        try:
            if account and account.promoter_id:
                data = provider_request("GET", f"{BASE}/{account.promoter_id}", headers=headers())
                data = data.get("data", data) if isinstance(data, dict) else data
                if not owned(data, request.user):
                    raise ProviderError("affiliate_identity_conflict")
            else:
                data = find_promoter(request.user)
                if data:
                    account, _ = AffiliateAccount.objects.get_or_create(user=request.user)
                    save_binding(account, data, request.user)
            if data:
                return Response({"configured": True, "status": "active", **public_data(data)})
            return Response(
                {
                    "configured": True,
                    "status": "needs_review"
                    if account and account.status in {"creating", "needs_review"}
                    else "not_enrolled",
                }
            )
        except ProviderError:
            return Response(
                {
                    "detail": "Your affiliate details could not be refreshed. Please try again later."
                },
                status=503,
            )

    def post(self, request):
        if not configured():
            return Response({"detail": "The referral program is not configured."}, status=503)
        if not request.user.email_verified_at:
            raise PermissionDenied("Verify your email address before joining the referral program.")
        # Serialize enrollment per account. Persist uncertainty before provider writes;
        # a disconnected request must never automatically create a second promoter.
        with transaction.atomic():
            account, _ = AffiliateAccount.objects.get_or_create(user=request.user)
            account = AffiliateAccount.objects.select_for_update().get(pk=account.pk)
            try:
                existing = find_promoter(request.user)
            except ProviderError:
                return Response(
                    {
                        "detail": "We could not check your affiliate account. Please try again later."
                    },
                    status=503,
                )
            if existing:
                try:
                    save_binding(account, existing, request.user)
                except ProviderError:
                    return Response(
                        {"detail": "Your affiliate account needs an ownership review."}, status=409
                    )
                return Response({"configured": True, "status": "active", **public_data(existing)})
            if account.status in {"creating", "needs_review", "active"}:
                return Response(
                    {"detail": "Your enrollment needs review before another creation attempt."},
                    status=409,
                )
            account.status, account.last_error = "creating", ""
            account.save(update_fields=["status", "last_error", "updated_at"])
        payload = {
            "email": request.user.email,
            "cust_id": customer_id(request.user),
            "drip_emails": False,
            "profile": {"first_name": request.user.first_name, "last_name": request.user.last_name},
        }
        if settings.FIRSTPROMOTER_CAMPAIGN_ID:
            payload["initial_campaign_id"] = settings.FIRSTPROMOTER_CAMPAIGN_ID
        try:
            data = provider_request("POST", BASE, headers=headers(), json=payload, side_effect=True)
            data = data.get("data", data) if isinstance(data, dict) else data
            save_binding(account, data, request.user)
        except ProviderError as exc:
            account.status = "new" if exc.code == "provider_rejected" else "needs_review"
            account.last_error = exc.code[:80]
            account.save(update_fields=["status", "last_error", "updated_at"])
            return Response(
                {
                    "detail": "Enrollment could not be confirmed. Refresh your affiliate account before trying again."
                },
                status=503,
            )
        return Response({"configured": True, "status": "active", **public_data(data)}, status=201)

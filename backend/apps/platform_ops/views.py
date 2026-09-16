import hashlib
import secrets
import time
import uuid
from datetime import timedelta
from functools import wraps

from django.contrib.auth import authenticate, login, logout
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.tenants.models import Workspace

from .models import (
    Control,
    OperationStatus,
    PlatformAudit,
    PlatformInvite,
    PlatformRole,
    SupportSession,
)
from .security import new_secret, record, verify_otp


def page(request, **context):
    return render(request, "platform_ops/console.html", context, status=context.pop("status", 200))


def role_for(request):
    if not request.user.is_authenticated or not request.user.is_active or not request.user.is_staff:
        return None
    return PlatformRole.objects.filter(user=request.user, active=True).first()


def valid_uuid(value):
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise Http404 from None


def login_allowed(request, identifier):
    keys = [
        "ops-login:" + hashlib.sha256(value.encode()).hexdigest()
        for value in [
            "account:" + identifier.casefold()[:254],
            "ip:" + request.META.get("REMOTE_ADDR", ""),
        ]
    ]
    for key in keys:
        if not cache.add(key, 1, timeout=900):
            try:
                if cache.incr(key) > 10:
                    return False
            except ValueError:
                return False
    return True


def protected(*roles):
    def decorate(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            role = role_for(request)
            if not role:
                return redirect("/ops/login/")
            proof = request.session.get("platform_mfa", {})
            if (
                not role.otp_confirmed
                or proof.get("version") != role.version
                or proof.get("until", 0) <= time.time()
            ):
                return redirect("/ops/mfa/")
            if roles and role.role not in roles:
                return HttpResponseForbidden("Your platform role cannot perform this action.")
            request.platform_role = role
            return view(request, *args, **kwargs)

        return wrapped

    return decorate


def sign_in(request):
    error = ""
    if request.method == "POST":
        # Count failures by client and account, without persisting raw login names.
        identifier = str(request.POST.get("username", "")).casefold()[:254]
        if not login_allowed(request, identifier):
            return page(
                request,
                screen="login",
                error="Too many attempts. Try again in 15 minutes.",
                status=429,
            )
        user = authenticate(
            request,
            username=request.POST.get("username", ""),
            password=request.POST.get("password", ""),
        )
        role = PlatformRole.objects.filter(user=user, active=True).first() if user else None
        if user and user.is_staff and role:
            login(request, user)
            request.session.pop("platform_mfa", None)
            request.session["platform_password_at"] = time.time()
            record(user, "platform.password_verified")
            return redirect("/ops/mfa/")
        error = "Invalid credentials or platform access unavailable."
    return page(request, screen="login", error=error)


def mfa(request):
    role = role_for(request)
    if not role or request.session.get("platform_password_at", 0) < time.time() - 600:
        return redirect("/ops/login/")
    with transaction.atomic():
        role = PlatformRole.objects.select_for_update().get(pk=role.pk)
        if not role.otp_secret:
            role.otp_secret = new_secret()
            role.save(update_fields=["otp_secret"])
    error = ""
    if request.method == "POST":
        if verify_otp(role.pk, request.POST.get("code", "")):
            request.session.cycle_key()
            request.session["platform_mfa"] = {"version": role.version, "until": time.time() + 1800}
            record(request.user, "platform.mfa_verified")
            return redirect("/ops/")
        error = "Invalid, reused or locked code."
    return page(
        request, screen="mfa", secret=role.otp_secret if not role.otp_confirmed else "", error=error
    )


@require_POST
def sign_out(request):
    if role_for(request):
        record(request.user, "platform.logout")
    logout(request)
    return redirect("/ops/login/")


@protected()
def dashboard(request):
    from django.conf import settings
    from redis import Redis, RedisError

    from apps.agents.models import UsageRecord
    from apps.billing.models import BillingAccount
    from apps.channels.models import ChannelConnection, Delivery, WebhookEvent
    from apps.crm.models import Message

    from .metrics import revenue_metrics
    from .models import DailyMetric

    start = timezone.now() - timedelta(days=30)
    query = request.GET.get("q", "")[:100]
    matches = Q(name__icontains=query)
    try:
        matches |= Q(pk=uuid.UUID(query))
    except ValueError:
        pass
    workspaces = Workspace.objects.filter(matches).annotate(
        total_cost=Sum("usagerecord__cost", filter=Q(usagerecord__created_at__gte=start)),
        total_calls=Count("usagerecord", filter=Q(usagerecord__created_at__gte=start)),
    )
    sort = request.GET.get("sort", "")
    workspaces = workspaces.order_by(
        {"cost": "-total_cost", "calls": "-total_calls"}.get(sort, "name"), "pk"
    )
    workspace_page = Paginator(workspaces, 25).get_page(request.GET.get("page"))
    metric_calls = dict(
        DailyMetric.objects.filter(day__gte=start.date(), name__startswith="meta.calls:")
        .values("name")
        .annotate(total=Sum("value"))
        .values_list("name", "total")
    )
    rows = []
    for workspace in workspace_page:
        account = BillingAccount.objects.for_workspace(workspace).first()
        usage = (
            UsageRecord.objects.for_workspace(workspace)
            .filter(created_at__gte=start)
            .aggregate(tokens=Sum("input_tokens"), cost=Sum("cost"), calls=Count("id"))
        )
        rows.append(
            {
                "workspace": workspace,
                "meta_calls": metric_calls.get("meta.calls:" + str(workspace.pk), 0),
                "account": account,
                "usage": usage,
                "channels": ChannelConnection.objects.for_workspace(workspace).count(),
                "failed": WebhookEvent.objects.for_workspace(workspace)
                .filter(status="failed")
                .count(),
                "suspended": Control.objects.filter(
                    scope=str(workspace.pk), key="workspace", disabled=True
                ).exists(),
            }
        )
    totals = UsageRecord.all_objects.filter(created_at__gte=start).aggregate(
        cost=Sum("cost"), tokens=Sum("input_tokens"), calls=Count("id")
    )
    try:
        redis = Redis.from_url(settings.REDIS_URL, socket_timeout=1, socket_connect_timeout=1)
        bucket = {
            "used": int(redis.get("rate:meta:app") or 0),
            "ttl": max(0, redis.ttl("rate:meta:app")),
            "limit": settings.META_APP_CALLS_PER_HOUR,
        }
    except RedisError:
        bucket = {"unavailable": True}
    return page(
        request,
        screen="dashboard",
        workspace_page=workspace_page,
        revenue=revenue_metrics(),
        billing_sync=cache.get("ops:billing_sync", "Not yet synchronized"),
        provider_metrics=DailyMetric.objects.filter(day__gte=start.date())
        .exclude(name__contains=":")
        .values("name")
        .annotate(total=Sum("value")),
        bucket=bucket,
        rows=rows,
        totals=totals,
        messages=Message.all_objects.filter(created_at__gte=start).count(),
        plans=BillingAccount.all_objects.values("plan", "status").annotate(total=Count("id")),
        delivery=Delivery.all_objects.filter(created_at__gte=start)
        .values("status")
        .annotate(total=Count("id")),
        connections=ChannelConnection.all_objects.select_related("workspace").order_by(
            "expires_at"
        )[:100],
        controls=Control.objects.filter(disabled=True),
        statuses=OperationStatus.objects.all(),
        staff=PlatformRole.objects.select_related("user").all(),
        invitations=PlatformInvite.objects.filter(
            used_at__isnull=True, expires_at__gt=timezone.now()
        ).order_by("expires_at")[:100]
        if request.platform_role.role == "owner"
        else [],
        logs=PlatformAudit.objects.all()[:100],
        role=request.platform_role.role,
        backlog=cache.get("operations:backlogs", {}),
    )


@require_POST
@protected("owner", "support")
@transaction.atomic
def control(request):
    scope = request.POST.get("workspace", "").strip()
    if scope:
        scope = valid_uuid(scope)
        get_object_or_404(Workspace, pk=scope)
    key = request.POST.get("key", "")
    allowed = {
        "workspace",
        "ai",
        "messaging",
        "automations",
        "content",
        "marketplace",
        "integration:google_calendar",
        "integration:calcom",
        "integration:airtable",
        "integration:notion",
        "integration:gohighlevel",
        "integration:slack",
        "integration:attio",
        "integration:elevenlabs",
        "integration:stripe",
        "integration:instagram",
        "integration:whatsapp",
        "integration:telegram",
        "integration:messenger",
    }
    if key.startswith("automation:") and scope:
        from apps.automations.models import Automation

        get_object_or_404(
            Automation.objects.for_workspace(scope), pk=valid_uuid(key.removeprefix("automation:"))
        )
    elif key not in allowed:
        return HttpResponseForbidden("Unknown control.")
    if not scope and request.platform_role.role != "owner":
        return HttpResponseForbidden("Only platform owners can change global controls.")
    reason = request.POST.get("reason", "").strip()[:300]
    if not reason:
        return HttpResponseForbidden("A reason is required.")
    if request.POST.get("disabled") not in {"true", "false"}:
        return HttpResponseForbidden("Choose pause or resume explicitly.")
    disabled = request.POST.get("disabled") == "true"
    item, _ = Control.objects.update_or_create(
        scope=scope, key=key, defaults={"disabled": disabled, "reason": reason}
    )
    record(request.user, "control.changed", scope, key=key, disabled=disabled, reason=reason)
    return redirect("/ops/")


@require_POST
@protected("owner")
@transaction.atomic
def staff_change(request):
    # Lock every role in stable order to protect the last active owner.
    list(PlatformRole.objects.select_for_update().order_by("pk"))
    if not str(request.POST.get("id", "")).isdigit():
        raise Http404
    target = get_object_or_404(PlatformRole, pk=request.POST.get("id"))
    role = request.POST.get("role")
    active = request.POST.get("active") == "true"
    if role not in {"owner", "support", "analyst"}:
        return HttpResponseForbidden("Unknown role.")
    if (
        target.role == "owner"
        and target.active
        and (not active or role != "owner")
        and PlatformRole.objects.filter(role="owner", active=True).count() <= 1
    ):
        return HttpResponseForbidden("The last platform owner cannot be removed.")
    target.role = role
    target.active = active
    target.version += 1
    target.save()
    record(request.user, "staff.changed", target=str(target.user_id), role=role, active=active)
    return redirect("/ops/")


@require_POST
@protected("owner")
def invite(request):
    from django.core.exceptions import ValidationError
    from django.core.validators import validate_email

    email = request.POST.get("email", "").strip().lower()
    role = request.POST.get("role", "")
    try:
        validate_email(email)
    except ValidationError:
        return HttpResponseForbidden("Valid email required.")
    if role not in {"owner", "support", "analyst"}:
        return HttpResponseForbidden("Unknown role.")
    token = secrets.token_urlsafe(32)
    with transaction.atomic():
        PlatformInvite.objects.create(
            email=email,
            role=role,
            digest=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=timezone.now() + timedelta(days=1),
        )
        record(request.user, "staff.invited", email=email, role=role)
    return page(request, screen="invite", token=token)


@require_POST
@protected("owner")
@transaction.atomic
def revoke_invite(request):
    if not request.POST.get("id", "").isdigit():
        raise Http404
    item = get_object_or_404(
        PlatformInvite.objects.select_for_update(), pk=request.POST["id"], used_at__isnull=True
    )
    item.expires_at = timezone.now()
    item.save(update_fields=["expires_at"])
    record(request.user, "staff.invite_revoked", target=str(item.pk))
    return redirect("/ops/")


def accept_invite(request):
    error = ""
    if request.method == "POST":
        if not login_allowed(request, request.POST.get("username", "")):
            return page(
                request,
                screen="accept",
                error="Too many attempts. Try again in 15 minutes.",
                status=429,
            )
        # Invitees use their existing account password; invitation possession alone is insufficient.
        user = authenticate(
            request,
            username=request.POST.get("username", ""),
            password=request.POST.get("password", ""),
        )
        if user:
            with transaction.atomic():
                invitation = (
                    PlatformInvite.objects.select_for_update()
                    .filter(
                        digest=hashlib.sha256(request.POST.get("token", "").encode()).hexdigest(),
                        email__iexact=user.email,
                        used_at__isnull=True,
                        expires_at__gt=timezone.now(),
                    )
                    .first()
                )
                if invitation and not PlatformRole.objects.filter(user=user).exists():
                    user.is_staff = True
                    user.save(update_fields=["is_staff"])
                    PlatformRole.objects.create(user=user, role=invitation.role)
                    invitation.used_at = timezone.now()
                    invitation.save()
                    record(user, "staff.invite_accepted")
                    return redirect("/ops/login/")
        error = "Invitation or credentials invalid."
    return page(request, screen="accept", error=error)


@require_POST
@protected("owner", "support")
def start_support(request):
    workspace = get_object_or_404(Workspace, pk=valid_uuid(request.POST.get("workspace")))
    reason = request.POST.get("reason", "").strip()[:300]
    if not reason:
        return HttpResponseForbidden("A support reason is required.")
    with transaction.atomic():
        session = SupportSession.objects.create(
            operator=request.platform_role,
            workspace=workspace,
            reason=reason,
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        record(
            request.user, "support.started", workspace.pk, session=str(session.pk), reason=reason
        )
    return redirect(f"/ops/support/{session.pk}/")


@protected("owner", "support")
def support(request, pk):
    from apps.crm.models import Conversation, Message

    session = get_object_or_404(
        SupportSession.objects.select_related("workspace"),
        pk=pk,
        operator=request.platform_role,
        ended_at__isnull=True,
        expires_at__gt=timezone.now(),
    )
    if request.method == "POST":
        with transaction.atomic():
            session.ended_at = timezone.now()
            session.save()
            record(request.user, "support.ended", session.workspace_id, session=str(session.pk))
        return redirect("/ops/")
    record(request.user, "support.viewed", session.workspace_id, session=str(session.pk))
    return page(
        request,
        screen="support",
        support=session,
        conversations=Conversation.objects.for_workspace(session.workspace_id).select_related(
            "identity__lead"
        )[:50],
        messages=Message.objects.for_workspace(session.workspace_id).order_by("-created_at")[:50],
    )


@require_POST
@protected("owner")
def operation_status(request):
    from django.utils.dateparse import parse_datetime

    provider = request.POST.get("provider", "")
    if provider not in {"instagram", "whatsapp", "messenger", "telegram"}:
        return HttpResponseForbidden("Unknown provider.")
    raw_expiry = request.POST.get("certificate_expires_at", "").strip()
    try:
        expiry = parse_datetime(raw_expiry) if raw_expiry else None
    except ValueError:
        expiry = None
    if raw_expiry and (not expiry or timezone.is_naive(expiry)):
        return page(
            request,
            error="Use an ISO date and time with timezone for certificate expiry.",
            status=400,
        )
    with transaction.atomic():
        OperationStatus.objects.update_or_create(
            provider=provider,
            defaults={
                "review_status": request.POST.get("review_status", "")[:100],
                "permissions": request.POST.get("permissions", "")[:1000],
                "certificate_expires_at": expiry,
            },
        )
        record(
            request.user,
            "operations.updated",
            provider=provider,
            review_status=request.POST.get("review_status", "")[:100],
            permissions=request.POST.get("permissions", "")[:1000],
            certificate_expiry=raw_expiry,
        )
    return redirect("/ops/")

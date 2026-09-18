"""User-level operations for the console's Users page (2.5.5).

A ban here is a cascade, not a flag:

1. the account cannot sign in, and any open session or bearer token stops working
   (enforced by `apps.tenants.auth`);
2. outstanding refresh tokens are blacklisted, so a stolen or saved refresh cannot
   mint a new access token;
3. every workspace the user owns is paused through the same `Control` kill switch
   operators already use, which stops webhook processing, automations, AI and
   outbound delivery for their connected accounts.

A workspace an operator had already suspended for another reason is left exactly as
it was, and unbanning only lifts the pauses the ban itself created.
"""

from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Max, Q, Sum
from django.utils import timezone

from .models import Control, PlatformAudit, SupportTicket
from .security import record

BAN_REASON_PREFIX = "Owner banned: "


def owned_workspace_ids(user):
    from apps.tenants.models import Membership

    return [
        str(pk)
        for pk in Membership.all_objects.filter(user=user, role="owner").values_list(
            "workspace_id", flat=True
        )
    ]


@transaction.atomic
def ban_user(user, *, operator, reason):
    reason = (reason or "").strip()[:300]
    if not reason:
        raise ValueError("A ban needs a reason.")
    if user.is_superuser:
        raise ValueError("A superuser cannot be banned from the console.")
    user.is_banned = True
    user.banned_at = timezone.now()
    user.ban_reason = reason
    user.save(update_fields=["is_banned", "banned_at", "ban_reason"])
    revoked = blacklist_tokens(user)
    paused = []
    for workspace_id in owned_workspace_ids(user):
        existing = Control.objects.filter(scope=workspace_id, key="workspace").first()
        # An independent operator suspension is not ours to overwrite or later lift.
        if existing and existing.disabled and not existing.reason.startswith(BAN_REASON_PREFIX):
            continue
        Control.objects.update_or_create(
            scope=workspace_id,
            key="workspace",
            defaults={"disabled": True, "reason": (BAN_REASON_PREFIX + reason)[:300]},
        )
        paused.append(workspace_id)
    record(
        operator,
        "user.banned",
        target=str(user.pk),
        reason=reason,
        paused=paused,
        tokens_revoked=revoked,
    )
    return paused


@transaction.atomic
def unban_user(user, *, operator, reason=""):
    user.is_banned = False
    user.banned_at = None
    user.ban_reason = ""
    user.save(update_fields=["is_banned", "banned_at", "ban_reason"])
    lifted = list(
        Control.objects.filter(
            scope__in=owned_workspace_ids(user),
            key="workspace",
            disabled=True,
            reason__startswith=BAN_REASON_PREFIX,
        ).values_list("scope", flat=True)
    )
    Control.objects.filter(scope__in=lifted, key="workspace").update(disabled=False)
    record(operator, "user.unbanned", target=str(user.pk), reason=reason[:300], lifted=lifted)
    return lifted


def blacklist_tokens(user):
    from rest_framework_simplejwt.token_blacklist.models import (
        BlacklistedToken,
        OutstandingToken,
    )

    count = 0
    for token in OutstandingToken.objects.filter(user=user):
        _, created = BlacklistedToken.objects.get_or_create(token=token)
        count += int(created)
    return count


@transaction.atomic
def create_user(*, name, email, password, operator, workspace_name=""):
    """Support-created accounts, migrations and test users. The account is created
    exactly as signup would create it, so nothing downstream can tell the difference."""
    import uuid

    from django.contrib.auth import get_user_model
    from django.contrib.auth.password_validation import validate_password
    from django.core.validators import validate_email

    from apps.tenants.services import create_workspace

    email = (email or "").strip().lower()
    validate_email(email)
    User = get_user_model()
    if User.objects.filter(email__iexact=email).exists():
        raise ValueError("An account with that email already exists.")
    validate_password(password)
    user = User.objects.create_user(
        username=str(uuid.uuid4()), email=email, first_name=(name or "")[:150], password=password
    )
    if workspace_name:
        create_workspace(user, workspace_name[:100])
    record(operator, "user.created", target=str(user.pk), email=email)
    return user


def user_rows(*, query="", status="", tier="", category="", joined="", page=1, per_page=24):
    """Search and filter across every account, with the per-user figures the cards
    show. Figures are computed per card, so the page size is what bounds the cost."""
    from django.core.paginator import Paginator

    from apps.tenants.models import User

    from .models import UserSegment

    users = User.objects.all()
    if query:
        users = users.filter(
            Q(email__icontains=query)
            | Q(first_name__icontains=query)
            | Q(membership__workspace__channelconnection__display_name__icontains=query)
        ).distinct()
    if status == "banned":
        users = users.filter(is_banned=True)
    elif status == "active":
        users = users.filter(is_banned=False)
    if tier:
        users = users.filter(
            membership__role="owner",
            membership__workspace__billingaccount__plan_price__plan__slug=tier,
        ).distinct()
    if category:
        users = users.filter(pk__in=UserSegment.objects.filter(category=category).values("user_id"))
    days = {"7": 7, "30": 30, "90": 90}.get(joined)
    if days:
        users = users.filter(date_joined__gte=timezone.now() - timedelta(days=days))
    paginator = Paginator(users.order_by("-date_joined", "-pk"), per_page)
    page_obj = paginator.get_page(page)
    ids = [user.pk for user in page_obj]
    return page_obj, [stats_for(user) for user in page_obj] if ids else []


def stats_for(user):
    from apps.agents.models import UsageRecord
    from apps.automations.models import Automation
    from apps.billing.models import BillingAccount
    from apps.channels.models import ChannelConnection
    from apps.crm.models import Message
    from apps.tenants.models import Membership

    from .models import UserSegment

    workspace_ids = list(
        Membership.all_objects.filter(user=user).values_list("workspace_id", flat=True)
    )
    connections = ChannelConnection.all_objects.filter(workspace_id__in=workspace_ids).exclude(
        status="disconnected"
    )
    per_provider = dict(
        connections.values_list("provider")
        .annotate(total=Count("id"))
        .values_list("provider", "total")
    )
    followers = 0
    for profile in connections.values_list("profile", flat=True):
        try:
            followers += int((profile or {}).get("followers_count") or 0)
        except (TypeError, ValueError):
            continue
    account = (
        BillingAccount.all_objects.filter(workspace_id__in=owned_workspace_ids(user))
        .select_related("plan_price__plan")
        .first()
    )
    tokens = UsageRecord.all_objects.filter(workspace_id__in=workspace_ids).aggregate(
        i=Sum("input_tokens"), o=Sum("output_tokens")
    )
    expired = connections.filter(expires_at__lt=timezone.now()).exists()
    return {
        "user": user,
        "workspaces": len(workspace_ids),
        "automations": Automation.all_objects.filter(workspace_id__in=workspace_ids).count(),
        "instagram": per_provider.get("instagram", 0),
        "whatsapp": per_provider.get("whatsapp", 0),
        "telegram": per_provider.get("telegram", 0),
        "followers": followers,
        "messages": Message.all_objects.filter(
            workspace_id__in=workspace_ids, direction="outbound"
        ).count(),
        "ai_tokens": (tokens["i"] or 0) + (tokens["o"] or 0),
        "plan": account.plan_obj.name if account else "Free",
        "plan_status": account.status if account else "",
        "token_expired": expired,
        "categories": sorted(
            set(UserSegment.objects.filter(user=user).values_list("category", flat=True))
        ),
        "owned": owned_workspace_ids(user),
    }


def leaderboard(limit=12):
    """Top accounts by messages sent, attributed to each workspace's owner."""
    from apps.crm.models import Message
    from apps.tenants.models import Membership, User

    per_workspace = dict(
        Message.all_objects.filter(direction="outbound")
        .values("workspace_id")
        .annotate(total=Count("id"))
        .values_list("workspace_id", "total")
    )
    totals = {}
    for membership in Membership.all_objects.filter(
        role="owner", workspace_id__in=per_workspace
    ).values("user_id", "workspace_id"):
        totals[membership["user_id"]] = totals.get(membership["user_id"], 0) + per_workspace.get(
            membership["workspace_id"], 0
        )
    ranked = sorted(totals.items(), key=lambda item: -item[1])[:limit]
    people = User.objects.in_bulk([user_id for user_id, _ in ranked])
    return [
        {"user": people[user_id], "messages": total}
        for user_id, total in ranked
        if user_id in people
    ]


def history_for(user, limit=60):
    """Everything that happened to this account, newest first: operator actions on
    the user, events in the workspaces they belong to, and their support tickets."""
    from apps.tenants.models import AuditEvent, Membership

    workspace_ids = [
        str(pk)
        for pk in Membership.all_objects.filter(user=user).values_list("workspace_id", flat=True)
    ]
    rows = []
    for item in PlatformAudit.objects.filter(
        Q(detail__target=str(user.pk)) | Q(workspace_id__in=workspace_ids)
    ).order_by("-created_at")[:limit]:
        rows.append({"at": item.created_at, "kind": "Operator", "action": item.action})
    for item in AuditEvent.all_objects.filter(
        Q(actor=user) | Q(workspace_id__in=workspace_ids)
    ).order_by("-created_at")[:limit]:
        rows.append({"at": item.created_at, "kind": "Workspace", "action": item.action})
    for ticket in SupportTicket.objects.filter(reporter_email__iexact=user.email)[:limit]:
        rows.append(
            {
                "at": ticket.created_at,
                "kind": "Ticket",
                "action": f"{ticket.ticket_number} {ticket.subject}",
            }
        )
    if user.last_login:
        rows.append({"at": user.last_login, "kind": "Sign-in", "action": "Last sign-in"})
    return sorted(rows, key=lambda row: row["at"], reverse=True)[:limit]


def last_seen(user):
    from apps.tenants.models import AuditEvent

    latest = AuditEvent.all_objects.filter(actor=user).aggregate(at=Max("created_at"))["at"]
    candidates = [value for value in [latest, user.last_login] if value]
    return max(candidates) if candidates else None

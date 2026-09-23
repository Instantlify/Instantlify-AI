"""One plan gate, used everywhere.

Views: `@require_feature("ai_agent_enabled")` / `@require_within_limit("team_seats")`,
or call `check_feature` / `check_within_limit` after the membership check.
Tasks: `guard(workspace_id, name)` returns False after auditing and notifying the
workspace, because a Celery task cannot raise an HTTP 402.

Limits come from the workspace's plan (`BillingAccount.limits`); nothing here reads a
setting or a hard-coded tier. A numeric limit of None means unlimited.
"""

from functools import wraps

from django.http import Http404
from rest_framework.exceptions import APIException

FEATURES = {
    "ai_agent_enabled": "The AI agent is not included in your plan.",
    "integrations_unlocked": "Integrations are not included in your plan.",
    "content_scheduling_enabled": "Content scheduling is not included in your plan.",
    "voice_notes_enabled": "Voice notes are not included in your plan.",
}
LIMIT_MESSAGES = {
    "max_instagram_accounts": "Your plan's connected-account limit has been reached.",
    "max_contacts": "Your plan's contact limit has been reached.",
    "team_seats": "Your plan's seat limit has been reached. Upgrade to add teammates.",
    "max_ai_messages": "The AI message limit for this billing period has been reached.",
}


class PlanLimitExceeded(APIException):
    """402 with a machine-readable `upgrade_required` naming the limit that blocked."""

    status_code = 402
    default_code = "plan_limit_exceeded"

    def __init__(self, limit, message=None):
        self.limit = limit
        super().__init__(
            {
                "detail": message
                or LIMIT_MESSAGES.get(limit)
                or FEATURES.get(limit)
                or "Upgrade required.",
                "code": self.default_code,
                "upgrade_required": limit,
            }
        )


def limits_for(workspace_id):
    from .services import account_for

    return account_for(workspace_id).limits


def check_feature(workspace_id, name):
    if name not in FEATURES:
        raise ValueError(f"Unknown plan feature: {name}")
    if not getattr(limits_for(workspace_id), name):
        raise PlanLimitExceeded(name)


def usage_of(workspace_id, name):
    """Current consumption of a numeric limit. Kept next to the limit definitions so a
    new limit means one counter here, not a search through the codebase."""
    if name == "max_instagram_accounts":
        from apps.channels.models import ChannelConnection

        return (
            ChannelConnection.objects.for_workspace(workspace_id)
            .exclude(status="disconnected")
            .count()
        )
    if name == "max_contacts":
        from apps.crm.models import Lead

        return Lead.objects.for_workspace(workspace_id).count()
    if name == "team_seats":
        from apps.tenants.invitations import open_invitations
        from apps.tenants.models import Membership

        return (
            Membership.objects.for_workspace(workspace_id).count()
            + open_invitations(workspace_id).count()
        )
    if name == "max_ai_messages":
        from apps.agents.models import UsageRecord

        from .services import account_for

        account = account_for(workspace_id)
        return (
            UsageRecord.objects.for_workspace(workspace_id)
            .filter(kind="generation", created_at__gte=account.period_start)
            .count()
        )
    raise ValueError(f"Unknown plan limit: {name}")


def check_within_limit(workspace_id, name, *, adding=1, current=None):
    """Raise unless `current + adding` fits the plan's cap. `current` may be supplied when
    the caller already holds the count (or counts differently, e.g. accepting an invite
    that itself occupies one of the open-invitation slots)."""
    cap = getattr(limits_for(workspace_id), name)
    if cap is None:
        return
    used = usage_of(workspace_id, name) if current is None else current
    if used + adding > cap:
        raise PlanLimitExceeded(name)


def _member_or_404(request, workspace_id):
    # Gate after membership so a stranger learns nothing about another tenant's plan.
    from apps.tenants.models import Membership

    if not Membership.objects.for_workspace(workspace_id).filter(user=request.user).exists():
        raise Http404


def require_feature(name):
    def decorate(fn):
        @wraps(fn)
        def wrapper(self, request, workspace_id, *args, **kwargs):
            _member_or_404(request, workspace_id)
            check_feature(workspace_id, name)
            return fn(self, request, workspace_id, *args, **kwargs)

        return wrapper

    return decorate


def require_within_limit(name, adding=1):
    def decorate(fn):
        @wraps(fn)
        def wrapper(self, request, workspace_id, *args, **kwargs):
            _member_or_404(request, workspace_id)
            check_within_limit(workspace_id, name, adding=adding)
            return fn(self, request, workspace_id, *args, **kwargs)

        return wrapper

    return decorate


def guard(workspace_id, name, *, adding=None):
    """Task-side gate. Returns True when allowed. When blocked it records an audit event
    and pushes a realtime hint so the workspace sees why work stopped, then returns
    False so the caller can fail its job cleanly instead of dropping it silently."""
    from apps.crm.services import notify
    from apps.tenants.models import Workspace
    from apps.tenants.services import audit

    try:
        if name in FEATURES:
            check_feature(workspace_id, name)
        else:
            check_within_limit(workspace_id, name, adding=1 if adding is None else adding)
    except PlanLimitExceeded:
        audit(Workspace.objects.get(pk=workspace_id), None, f"plan.blocked:{name}"[:80], "")
        notify(workspace_id)
        return False
    return True


def locked_connection_ids(workspace_id):
    """Soft-lock after a downgrade: connections beyond the plan's cap keep receiving and
    replying, but are read-only for new configuration (no scheduled posts, no test
    simulation) until the workspace is back within its limit. The oldest connections
    stay usable; the newest are locked, so nothing a customer relied on first disappears."""
    from apps.channels.models import ChannelConnection

    cap = limits_for(workspace_id).max_instagram_accounts
    if cap is None:
        return set()
    ids = list(
        ChannelConnection.objects.for_workspace(workspace_id)
        .exclude(status="disconnected")
        .order_by("created_at", "id")
        .values_list("pk", flat=True)
    )
    return set(ids[cap:])


def check_connection_unlocked(connection):
    if connection.pk in locked_connection_ids(connection.workspace_id):
        raise PlanLimitExceeded(
            "max_instagram_accounts",
            "This account is locked because your plan allows fewer connected accounts. "
            "It still receives and replies; upgrade or disconnect another account to edit it.",
        )

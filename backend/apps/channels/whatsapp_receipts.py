"""Signed webhook receipts update delivery progress, without creating customer messages."""

from datetime import UTC, datetime

from django.utils import timezone

from .models import Delivery


def receive_receipt(event, payload):
    from apps.crm.services import notify

    item = (
        Delivery.objects.for_workspace(event.workspace_id)
        .select_for_update()
        .filter(
            connection=event.connection,
            provider_message_id=payload["message_id"],
            recipient_id=payload["recipient_id"],
        )
        .first()
    )
    if not item:
        # The receipt can arrive before the sender commits Meta's message ID.
        if event.created_at > timezone.now() - timezone.timedelta(minutes=2):
            raise ValueError("Receipt arrived before delivery was saved")
        return
    order = {"": 0, "sent": 1, "failed": 2, "delivered": 3, "read": 4}
    status = payload["status"]
    if order[status] <= order.get(item.provider_status, 0):
        return
    try:
        when = datetime.fromtimestamp(int(payload["timestamp"]), tz=UTC)
    except (ValueError, TypeError, OverflowError, OSError):
        when = timezone.now()
    item.provider_status = status
    item.provider_status_at = when
    item.save(update_fields=["provider_status", "provider_status_at"])
    from django.db import transaction

    transaction.on_commit(lambda: notify(event.workspace_id))

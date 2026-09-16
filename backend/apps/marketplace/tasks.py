from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.channels.transport import ProviderError

from .models import SellerAccount, TemplatePurchase
from .services import CHECKOUT_TTL, sync_seller


@shared_task(ignore_result=True)
def refresh_sellers():
    """Periodic capability re-check so a restricted author stops appearing purchasable
    even if no buyer has touched their template (buyers also trigger a fresh check)."""
    stale = timezone.now() - timedelta(hours=12)
    for seller in SellerAccount.all_objects.filter(checked_at__lt=stale)[:500]:
        try:
            sync_seller(seller)
        except (ProviderError, ValueError):
            continue


@shared_task(ignore_result=True)
def expire_purchases():
    """Stripe Checkout sessions expire after 24h; a pending row older than that is dead."""
    TemplatePurchase.all_objects.filter(
        status="pending", created_at__lt=timezone.now() - CHECKOUT_TTL
    ).update(status="expired")

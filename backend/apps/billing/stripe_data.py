"""Normalize Stripe SDK responses before applying dictionary-based domain logic."""

import stripe


def stripe_data(value):
    # StripeObject implements indexing, but current SDK versions do not expose dict.get.
    # The public conversion recursively handles metadata, items and expanded resources.
    return value.to_dict() if isinstance(value, stripe.StripeObject) else value

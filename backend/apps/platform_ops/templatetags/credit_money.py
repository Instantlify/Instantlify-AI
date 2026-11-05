from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def credit_money(value):
    """Preserve sub-cent credit charges while keeping ordinary amounts concise."""
    try:
        amount = Decimal(str(value))
        if not amount.is_finite():
            return "0.00"
        if amount == amount.quantize(Decimal("0.01")):
            return f"{amount:,.2f}"
        return f"{amount:,.6f}".rstrip("0")
    except (InvalidOperation, ValueError, TypeError):
        return "0.00"

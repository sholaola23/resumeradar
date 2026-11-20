"""One rounding rule for every percentage ResumeRadar shows.

The browser uses Math.round, which rounds halves up (42.5 -> 43). Python's
round() rounds halves to the even number (42.5 -> 42) and int() cuts the
decimals off, so the same scan could show 43% on the ring, 42% in the
summary and 42% in the email. Server-side text uses this helper instead.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def whole_percent(value):
    """Round a percentage to a whole number, halves up, as the browser does.

    Returns 0 for anything that is not a finite number, because the email
    route passes client-supplied values through here.
    """
    if isinstance(value, bool):
        return 0
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return 0
    if not number.is_finite():
        return 0
    return int(number.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

from __future__ import annotations

from decimal import Decimal, InvalidOperation


ZERO = Decimal("0")


def parse_money(value, *, default: Decimal | None = ZERO) -> Decimal:
    if value is None:
        if default is None:
            raise InvalidOperation
        return default

    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))

    text = str(value).strip()
    if not text:
        if default is None:
            raise InvalidOperation
        return default

    text = (
        text.replace("$", "")
        .replace("COP", "")
        .replace("cop", "")
        .replace("\xa0", "")
        .replace(" ", "")
        .strip()
    )

    negative = text.startswith("-")
    if negative:
        text = text[1:]

    if not text:
        if default is None:
            raise InvalidOperation
        return default

    if "." in text and "," in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        if text.count(",") == 1 and 0 < len(text.split(",")[1]) <= 2:
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "." in text:
        if not (text.count(".") == 1 and 0 < len(text.split(".")[1]) <= 2):
            text = text.replace(".", "")

    if text.count(".") > 1:
        raise InvalidOperation

    amount = Decimal(text)
    return -amount if negative else amount


def format_money(value, *, with_symbol: bool = True) -> str:
    try:
        amount = parse_money(value)
    except (InvalidOperation, TypeError, ValueError):
        amount = ZERO

    sign = "-" if amount < 0 else ""
    amount = abs(amount).quantize(Decimal("0.01"))
    integer_part = int(amount)
    decimal_part = int((amount - Decimal(integer_part)) * 100)
    integer_text = format(integer_part, ",").replace(",", ".")

    if decimal_part:
        amount_text = f"{integer_text},{decimal_part:02d}"
    else:
        amount_text = integer_text

    if with_symbol:
        return f"{sign}$ {amount_text}"
    return f"{sign}{amount_text}"


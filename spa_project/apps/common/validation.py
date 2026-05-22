import re
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import EmailValidator
from django.utils import timezone


NAME_RE = re.compile(r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ\s'-]+$")
BASIC_TEXT_RE = re.compile(r"^[0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ\s.,:;()#%/+&_-]+$")
DIGITS_RE = re.compile(r"^\d+$")
PASSWORD_HAS_LETTER_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]")
PASSWORD_HAS_DIGIT_RE = re.compile(r"\d")
LOT_RE = re.compile(r"^[0-9A-Za-z-]+$")


def compact_whitespace(value):
    return " ".join(str(value or "").strip().split())


def normalize_person_name(value):
    value = compact_whitespace(value)
    return " ".join(part[:1].upper() + part[1:].lower() for part in value.split(" ") if part)


def validate_name(value, *, label, min_length=3, max_length=25):
    value = compact_whitespace(value)
    if not value:
        raise ValueError(f"{label} es obligatorio.")
    if len(value) < min_length:
        raise ValueError(f"{label} debe tener al menos {min_length} caracteres.")
    if len(value) > max_length:
        raise ValueError(f"{label} no puede superar {max_length} caracteres.")
    if not NAME_RE.fullmatch(value):
        raise ValueError(f"{label} solo permite letras, espacios, apostrofes y guiones.")
    return normalize_person_name(value)


def validate_basic_text(
    value,
    *,
    label,
    min_length,
    max_length,
    required=True,
):
    value = compact_whitespace(value)
    if not value:
        if required:
            raise ValueError(f"{label} es obligatorio.")
        return ""
    if len(value) < min_length:
        raise ValueError(f"{label} debe tener al menos {min_length} caracteres.")
    if len(value) > max_length:
        raise ValueError(f"{label} no puede superar {max_length} caracteres.")
    if not BASIC_TEXT_RE.fullmatch(value):
        raise ValueError(f"{label} contiene caracteres no permitidos.")
    return value


def validate_digits_string(value, *, label, min_length, max_length, required=True):
    value = compact_whitespace(value)
    if not value:
        if required:
            raise ValueError(f"{label} es obligatorio.")
        return ""
    if not DIGITS_RE.fullmatch(value):
        raise ValueError(f"{label} solo permite numeros.")
    if len(value) < min_length:
        raise ValueError(f"{label} debe tener al menos {min_length} digitos.")
    if len(value) > max_length:
        raise ValueError(f"{label} no puede superar {max_length} digitos.")
    return value


def validate_email(value, *, label="El correo", required=True, max_length=100):
    value = compact_whitespace(value).lower()
    if not value:
        if required:
            raise ValueError(f"{label} es obligatorio.")
        return ""
    if len(value) > max_length:
        raise ValueError(f"{label} no puede superar {max_length} caracteres.")
    try:
        EmailValidator(message=f"{label} no es valido.")(value)
    except DjangoValidationError as exc:
        raise ValueError(exc.messages[0]) from exc
    return value


def validate_birth_date(value, *, minimum_age=18):
    raw = compact_whitespace(value)
    if not raw:
        raise ValueError("La fecha de nacimiento es obligatoria.")
    try:
        birth_date = date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("La fecha de nacimiento no es valida.") from exc

    today = timezone.localdate()
    if birth_date > today:
        raise ValueError("La fecha de nacimiento no puede estar en el futuro.")

    age = today.year - birth_date.year - (
        (today.month, today.day) < (birth_date.month, birth_date.day)
    )
    if age < minimum_age:
        raise ValueError("Debes ser mayor de edad para continuar.")
    return birth_date


def validate_password(value, *, label="La contrasena", min_length=8, max_length=30):
    value = str(value or "").strip()
    if not value:
        raise ValueError(f"{label} es obligatoria.")
    if len(value) < min_length:
        raise ValueError(f"{label} debe tener al menos {min_length} caracteres.")
    if len(value) > max_length:
        raise ValueError(f"{label} no puede superar {max_length} caracteres.")
    if not PASSWORD_HAS_LETTER_RE.search(value) or not PASSWORD_HAS_DIGIT_RE.search(value):
        raise ValueError(f"{label} debe incluir al menos una letra y un numero.")
    return value


def validate_positive_int(value, *, label, min_value=1, max_value=None):
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f"{label} debe ser un numero entero valido.")
    if parsed < min_value:
        if min_value == 1:
            raise ValueError(f"{label} debe ser mayor a cero.")
        raise ValueError(f"{label} debe ser mayor o igual a {min_value}.")
    if max_value is not None and parsed > max_value:
        raise ValueError(f"{label} no puede superar {max_value}.")
    return parsed


def validate_decimal_range(
    value,
    *,
    label,
    min_value=None,
    max_value=None,
    allow_zero=False,
):
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError, TypeError, ValueError):
        raise ValueError(f"{label} debe ser un numero valido.")

    if min_value is not None:
        if allow_zero and parsed < min_value:
            raise ValueError(f"{label} no puede ser menor a {min_value}.")
        if not allow_zero and parsed <= min_value:
            if min_value == 0:
                raise ValueError(f"{label} debe ser mayor a cero.")
            raise ValueError(f"{label} debe ser mayor a {min_value}.")
    elif allow_zero:
        if parsed < 0:
            raise ValueError(f"{label} no puede ser negativo.")
    elif parsed <= 0:
        raise ValueError(f"{label} debe ser mayor a cero.")

    if max_value is not None and parsed > max_value:
        raise ValueError(f"{label} no puede superar {max_value}.")
    return parsed


def validate_percentage(value, *, label):
    return validate_decimal_range(
        value,
        label=label,
        min_value=0,
        max_value=100,
        allow_zero=True,
    )


def validate_lote(value, *, label="El lote", max_length=8):
    value = compact_whitespace(value)
    if not value:
        raise ValueError(f"{label} es obligatorio.")
    if len(value) > max_length:
        raise ValueError(f"{label} no puede superar {max_length} caracteres.")
    if not LOT_RE.fullmatch(value):
        raise ValueError(f"{label} solo permite letras, numeros y guiones.")
    return value.upper()

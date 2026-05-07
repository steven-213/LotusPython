from datetime import timedelta
import secrets

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import send_mail
from django.utils import timezone


class MailDeliveryError(Exception):
    pass


def normalize_email(value: str) -> str:
    return (value or "").strip().lower()


def generate_verification_code() -> str:
    return f"{secrets.randbelow(1000000):06d}"


def hash_secret(raw_value: str) -> str:
    return make_password(raw_value)


def secret_matches(raw_value: str, encoded_value: str) -> bool:
    try:
        return check_password(raw_value, encoded_value)
    except ValueError:
        return encoded_value == raw_value


def get_code_expiration():
    minutes = getattr(settings, "ACCOUNT_SECURITY_CODE_TTL_MINUTES", 15)
    return timezone.now() + timedelta(minutes=minutes)


def get_code_ttl_minutes() -> int:
    return getattr(settings, "ACCOUNT_SECURITY_CODE_TTL_MINUTES", 15)


def set_usuario_password(usuario, raw_password: str) -> None:
    usuario.clave = make_password(raw_password)


def check_usuario_password(usuario, raw_password: str) -> bool:
    if not raw_password:
        return False

    stored_password = usuario.clave or ""
    try:
        if check_password(raw_password, stored_password):
            return True
    except ValueError:
        pass

    if stored_password == raw_password:
        usuario.clave = make_password(raw_password)
        usuario.save(update_fields=["clave"])
        return True

    return False


def send_registration_code_email(to_email: str, code: str) -> None:
    _send_code_email(
        to_email=to_email,
        code=code,
        action_label="confirmar tu cuenta",
    )


def send_password_reset_code_email(to_email: str, code: str) -> None:
    _send_code_email(
        to_email=to_email,
        code=code,
        action_label="restablecer tu contrasena",
    )


def _send_code_email(*, to_email: str, code: str, action_label: str) -> None:
    ttl_minutes = get_code_ttl_minutes()
    subject = f"Lotus Dream Spa | Codigo de verificacion"
    message = (
        "Hola,\n\n"
        f"Tu codigo para {action_label} es: {code}\n\n"
        f"Este codigo vence en {ttl_minutes} minutos.\n\n"
        "Si no realizaste esta solicitud, puedes ignorar este mensaje."
    )
    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [to_email],
            fail_silently=False,
        )
    except Exception as exc:  # pragma: no cover - depende del backend configurado
        raise MailDeliveryError(str(exc)) from exc

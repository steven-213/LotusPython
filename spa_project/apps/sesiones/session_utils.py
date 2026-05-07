from django.conf import settings
from django.utils import timezone


SESSION_STARTED_AT_KEY = "usuario_session_started_at"
SESSION_EXPIRES_AT_KEY = "usuario_session_expires_at"


def _now_timestamp():
    return int(timezone.now().timestamp())


def _coerce_timestamp(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def get_manual_session_timeout_seconds():
    configured_timeout = getattr(settings, "MANUAL_SESSION_TIMEOUT_SECONDS", 3600)
    return max(int(configured_timeout), 1)


def iniciar_sesion_manual(request, usuario):
    now_ts = _now_timestamp()
    expires_at = now_ts + get_manual_session_timeout_seconds()

    request.session.cycle_key()
    request.session["usuario_id"] = usuario.id
    request.session["usuario_rol"] = usuario.rol
    request.session["usuario_nombre"] = f"{usuario.nombre} {usuario.apellido}".strip()
    request.session[SESSION_STARTED_AT_KEY] = now_ts
    request.session[SESSION_EXPIRES_AT_KEY] = expires_at
    request.session.set_expiry(get_manual_session_timeout_seconds())

    request.manual_session_expired = False
    request.manual_session_expires_at = expires_at


def asegurar_vencimiento_sesion(request):
    request._manual_session_checked = True
    usuario_id = request.session.get("usuario_id")
    request.manual_session_expired = False
    request.manual_session_expires_at = None

    if not usuario_id:
        return False

    now_ts = _now_timestamp()
    expires_at = _coerce_timestamp(request.session.get(SESSION_EXPIRES_AT_KEY))
    started_at = _coerce_timestamp(request.session.get(SESSION_STARTED_AT_KEY))

    if expires_at is None:
        started_at = started_at or now_ts
        expires_at = started_at + get_manual_session_timeout_seconds()
        request.session[SESSION_STARTED_AT_KEY] = started_at
        request.session[SESSION_EXPIRES_AT_KEY] = expires_at
        request.session.modified = True

    if expires_at <= now_ts:
        request.manual_session_expired = True
        request.session.flush()
        return False

    request.manual_session_expires_at = expires_at
    request.session.set_expiry(max(expires_at - now_ts, 1))
    return True

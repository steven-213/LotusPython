import json
import logging
import ssl
from urllib import error, parse, request

from django.conf import settings

from apps.common.currency import format_money

logger = logging.getLogger(__name__)


def _limpiar_token(token):
    # Quita espacios y el prefijo "bot" si llega incluido.
    token = (token or "").strip()
    if token.startswith("bot"):
        return token[3:]
    return token


def _obtener_config_telegram():
    token = _limpiar_token(getattr(settings, "TELEGRAM_BOT_TOKEN", ""))
    chat_ids = list(getattr(settings, "TELEGRAM_CHAT_IDS", []) or [])
    chat_id_legacy = str(getattr(settings, "TELEGRAM_CHAT_ID", "") or "")
    legacy_items = [
        item.strip().strip('"').strip("'")
        for item in chat_id_legacy.split(",")
        if item.strip()
    ]
    for chat_id in legacy_items:
        if chat_id and chat_id not in chat_ids:
            chat_ids.append(chat_id)

    if not token or not chat_ids:
        logger.warning(
            "Telegram notifier disabled: missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID(S)."
        )
        return None, []
    return token, chat_ids


def _construir_url_telegram(path):
    base_url = str(getattr(settings, "APP_BASE_URL", "")).rstrip("/")
    confirm_token = getattr(settings, "TELEGRAM_CONFIRM_TOKEN", "")
    if not base_url or not confirm_token:
        return ""
    return f"{base_url}{path}?token={confirm_token}"


def _enviar_mensaje_chat_telegram(token, chat_id, text):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    req = request.Request(
        url,
        data=parse.urlencode(payload).encode("utf-8"),
        method="POST",
    )

    verify_ssl = bool(getattr(settings, "TELEGRAM_VERIFY_SSL", True))
    context = None if verify_ssl else ssl._create_unverified_context()

    try:
        with request.urlopen(req, timeout=10, context=context) as response:
            data = json.loads(response.read().decode("utf-8"))
            ok = response.status == 200 and bool(data.get("ok"))
            if not ok:
                logger.error("Telegram API returned non-ok response for chat %s: %s", chat_id, data)
            return ok
    except error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8")
        except Exception:
            body = str(exc)
        logger.error("Telegram HTTPError %s for chat %s: %s", exc.code, chat_id, body)
        return False
    except (error.URLError, TimeoutError, json.JSONDecodeError, ssl.SSLError) as exc:
        logger.error("Telegram notify failed for chat %s: %s", chat_id, exc)
        return False


def _enviar_mensaje_telegram(text):
    token, chat_ids = _obtener_config_telegram()
    if not token or not chat_ids:
        return False

    resultados = [_enviar_mensaje_chat_telegram(token, chat_id, text) for chat_id in chat_ids]
    enviados = sum(1 for resultado in resultados if resultado)
    if enviados and enviados != len(chat_ids):
        logger.warning(
            "Telegram notification reached %s of %s configured chats.",
            enviados,
            len(chat_ids),
        )
    return enviados > 0


def notificar_compra_pendiente(venta, validacion):
    logger.info(f"[INICIO] notificar_compra_pendiente - Validacion ID: {validacion.id}, Estado ANTES: '{validacion.estado}'")

    confirm_url = _construir_url_telegram(f"/ventas/telegram/confirm/{validacion.id}/")
    reject_url = _construir_url_telegram(f"/ventas/telegram/reject/{validacion.id}/")

    text = (
        "Nueva compra pendiente de confirmacion\n"
        f"Venta: #{venta.id}\n"
        f"Cliente: {venta.cliente_nombre_completo}\n"
        f"Monto: {format_money(validacion.monto)}\n"
        f"Metodo: {validacion.metodo_pago or 'N/A'}\n"
        f"Referencia: {validacion.referencia_pago or 'N/A'}\n"
        f"Estado: {validacion.estado}"
    )
    if confirm_url and reject_url:
        text += f"\n\nConfirmar compra: {confirm_url}\nRechazar compra: {reject_url}"

    ok = _enviar_mensaje_telegram(text)
    logger.info(f"[FIN] notificar_compra_pendiente - Mensaje enviado: {ok}, Estado DESPUÉS: '{validacion.estado}'")
    return ok


def notificar_solicitud_devolucion(solicitud):
    producto = solicitud.detalle_venta.producto
    venta = solicitud.detalle_venta.venta
    cliente = solicitud.cliente

    approve_url = _construir_url_telegram(
        f"/ventas/telegram/returns/{solicitud.id}/approve/"
    )
    reject_url = _construir_url_telegram(
        f"/ventas/telegram/returns/{solicitud.id}/reject/"
    )

    text = (
        "Nueva solicitud de devolucion\n"
        f"Solicitud: #{solicitud.id}\n"
        f"Venta: #{venta.id}\n"
        f"Cliente: {cliente.nombre} {cliente.apellido}\n"
        f"Producto: {producto.nombre}\n"
        f"Cantidad: {solicitud.cantidad}\n"
        f"Motivo: {solicitud.motivo}\n"
        f"Estado: {solicitud.estado}"
    )
    if approve_url and reject_url:
        text += f"\n\nAprobar devolucion: {approve_url}\nRechazar devolucion: {reject_url}"

    return _enviar_mensaje_telegram(text)

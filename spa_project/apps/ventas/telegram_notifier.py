import json
import logging
import ssl
from urllib import error, parse, request

from django.conf import settings

logger = logging.getLogger(__name__)


def _limpiar_token(token):
    # Quita espacios y el prefijo "bot" si llega incluido.
    token = (token or "").strip()
    if token.startswith("bot"):
        return token[3:]
    return token


def notificar_compra_pendiente(venta, validacion):
    logger.info(f"[INICIO] notificar_compra_pendiente - Validacion ID: {validacion.id}, Estado ANTES: '{validacion.estado}'")
    
    token = _limpiar_token(getattr(settings, "TELEGRAM_BOT_TOKEN", ""))
    chat_id = getattr(settings, "TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        logger.warning("Telegram notifier disabled: missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID.")
        return False

    base_url = str(getattr(settings, "APP_BASE_URL", "")).rstrip("/")
    confirm_token = getattr(settings, "TELEGRAM_CONFIRM_TOKEN", "")
    confirm_url = ""
    reject_url = ""
    if base_url and confirm_token:
        confirm_url = f"{base_url}/ventas/telegram/confirm/{validacion.id}/?token={confirm_token}"
        reject_url = f"{base_url}/ventas/telegram/reject/{validacion.id}/?token={confirm_token}"

    text = (
        "Nueva compra pendiente de confirmacion\n"
        f"Venta: #{venta.id}\n"
        f"Cliente: {venta.cliente.nombre} {venta.cliente.apellido}\n"
        f"Monto: {validacion.monto}\n"
        f"Metodo: {validacion.metodo_pago or 'N/A'}\n"
        f"Referencia: {validacion.referencia_pago or 'N/A'}\n"
        f"Estado: {validacion.estado}"
    )
    if confirm_url and reject_url:
        text += f"\n\nConfirmar compra: {confirm_url}\nRechazar compra: {reject_url}"

    # Evita que Telegram haga previsualización (prefetch) de los links,
    # lo cual puede disparar los endpoints de confirmación sin clic humano.
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
                logger.error("Telegram API returned non-ok response: %s", data)
            logger.info(f"[FIN] notificar_compra_pendiente - Mensaje enviado: {ok}, Estado DESPUÉS: '{validacion.estado}'")
            return ok
    except error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8")
        except Exception:
            body = str(exc)
        logger.error("Telegram HTTPError %s: %s", exc.code, body)
        logger.info(f"[ERROR] notificar_compra_pendiente - HTTPError, Estado DESPUÉS: '{validacion.estado}'")
        return False
    except (error.URLError, TimeoutError, json.JSONDecodeError, ssl.SSLError) as exc:
        logger.error("Telegram notify failed: %s", exc)
        logger.info(f"[ERROR] notificar_compra_pendiente - Exception, Estado DESPUÉS: '{validacion.estado}'")
        return False

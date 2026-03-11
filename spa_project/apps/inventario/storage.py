import logging
from pathlib import Path
from uuid import uuid4
from urllib import error, request

from django.conf import settings
from django.utils.text import slugify

logger = logging.getLogger(__name__)


def _crear_nombre_archivo(nombre_original: str) -> str:
    nombre = Path(nombre_original or "imagen").stem
    extension = Path(nombre_original or "").suffix.lower()
    slug = slugify(nombre) or "imagen"
    return f"productos/{uuid4().hex}-{slug}{extension}"


def subir_imagen_producto(archivo):
    if not archivo:
        return ""

    base_url = str(getattr(settings, "SUPABASE_URL", "")).rstrip("/")
    bucket = str(getattr(settings, "SUPABASE_STORAGE_BUCKET", "")).strip()
    service_key = str(getattr(settings, "SUPABASE_SERVICE_ROLE_KEY", "")).strip()

    if not base_url or not bucket or not service_key:
        logger.warning("Supabase storage not configured. Missing URL, bucket, or service key.")
        return ""

    nombre_archivo = _crear_nombre_archivo(getattr(archivo, "name", "imagen"))
    upload_url = f"{base_url}/storage/v1/object/{bucket}/{nombre_archivo}"

    headers = {
        "Authorization": f"Bearer {service_key}",
        "apikey": service_key,
        "Content-Type": getattr(archivo, "content_type", "application/octet-stream"),
        "x-upsert": "true",
    }

    data = archivo.read()
    req = request.Request(upload_url, data=data, headers=headers, method="POST")

    try:
        with request.urlopen(req, timeout=15) as response:
            if response.status not in {200, 201}:
                logger.error("Supabase upload failed with status %s", response.status)
                return ""
    except error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8")
        except Exception:
            body = str(exc)
        logger.error("Supabase upload HTTPError %s: %s", exc.code, body)
        return ""
    except Exception as exc:
        logger.error("Supabase upload failed: %s", exc)
        return ""

    return f"{base_url}/storage/v1/object/public/{bucket}/{nombre_archivo}"

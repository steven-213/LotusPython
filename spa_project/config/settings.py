"""
Django settings for the reorganized spa project.
"""

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

# === DIRECCIONES BASE ===
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

# Carga de variables de entorno locales
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(ENV_FILE, override=True)
except Exception:
    if ENV_FILE.exists():
        for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ[key] = value

# === FUNCIONES UTILERÍAS ===
def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value.strip())
    except (TypeError, ValueError):
        return default


def _env_list(name: str) -> list[str]:
    raw = os.getenv(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def _env_telegram_chat_ids() -> list[str]:
    chat_ids = _env_list("TELEGRAM_CHAT_IDS")
    legacy_raw = os.getenv("TELEGRAM_CHAT_ID", "")
    legacy_items = [
        item.strip().strip('"').strip("'")
        for item in legacy_raw.split(",")
        if item.strip()
    ]
    for chat_id in legacy_items:
        if chat_id and chat_id not in chat_ids:
            chat_ids.append(chat_id)
    return chat_ids


# === CONFIGURACIÓN DE SEGURIDAD GENERAL ===
# Clave secreta con fallback seguro para evitar bloqueos en Railway
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-lotus-dream-spa-key-despliegue-2026")

DEBUG = _env_bool("DJANGO_DEBUG", False)

# Permite conectar desde cualquier Host y asegura los dominios de Railway
ALLOWED_HOSTS = ['*']

CSRF_TRUSTED_ORIGINS = [
    'https://lotuspython-production.up.railway.app',
    'https://*.railway.app'
]

# Cabecera Proxy crucial para evitar el Error 403 (CSRF) en Railway
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')


# === APLICACIONES INSTALADAS ===
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.sitemaps",
    "django.contrib.staticfiles",
    "apps.common",
    "apps.sesiones.apps.SesionesConfig",
    "apps.inventario",
    "apps.ventas",
    "apps.citas",
]

# === MIDDLEWARES ===
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # Manejo optimizado de archivos estáticos
    "django.middleware.gzip.GZipMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.http.ConditionalGetMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

# === PLANTILLAS / TEMPLATES ===
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.common.context_processors.admin_shell",
            ],
            "builtins": [
                "apps.common.templatetags.money_tags",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


# === CONFIGURACIÓN DE BASE DE DATOS INTERNA ===
def _database_from_url(url: str):
    parsed = urlparse(url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError(f"Unsupported database scheme: {parsed.scheme}")
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": (parsed.path or "").lstrip("/") or "postgres",
        "USER": parsed.username or "",
        "PASSWORD": parsed.password or "",
        "HOST": parsed.hostname or "",
        "PORT": str(parsed.port or 5432),
        "OPTIONS": {"sslmode": "require"},
    }

# === CONTROL INTELIGENTE DE CONEXIÓN LOCAL vs NUBE ===
if os.getenv("RAILWAY_ENVIRONMENT"):
    # === EN PRODUCCIÓN (RAILWAY) ===
    DATABASE_URL = "postgresql://postgres:KrqwmMvsaQkqfZsWWRFZKKPpJMauQxPf@postgres.railway.internal:5432/railway"  
    DATABASES = {"default": _database_from_url(DATABASE_URL)}
else:
    # === EN TU COMPUTADORA (LOCAL) ===
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# Optimización de conexiones activas
for database_config in DATABASES.values():
    database_config.setdefault("CONN_MAX_AGE", _env_int("DB_CONN_MAX_AGE", 60))
    database_config.setdefault("CONN_HEALTH_CHECKS", True)


# === VALIDACIÓN DE CONTRASEÑAS ===
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# === LOCALIZACIÓN ===
LANGUAGE_CODE = "es-co"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

# === CACHÉ ===
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "lotus-local-cache",
        "TIMEOUT": _env_int("DJANGO_CACHE_TIMEOUT", 300),
    }
}

PUBLIC_CATALOG_CACHE_TIMEOUT = _env_int("PUBLIC_CATALOG_CACHE_TIMEOUT", 300)
PUBLIC_PAGE_CACHE_TIMEOUT = _env_int("PUBLIC_PAGE_CACHE_TIMEOUT", 600)

# === ARCHIVOS ESTÁTICOS Y MULTIMEDIA ===
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Almacenamiento optimizado para WhiteNoise
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# === INTEGRACIÓN TELEGRAM ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_IDS = _env_telegram_chat_ids()
TELEGRAM_CHAT_ID = TELEGRAM_CHAT_IDS[0] if TELEGRAM_CHAT_IDS else ""
TELEGRAM_CONFIRM_TOKEN = os.getenv("TELEGRAM_CONFIRM_TOKEN", "")
APP_BASE_URL = os.getenv("APP_BASE_URL", "")
TELEGRAM_VERIFY_SSL = _env_bool("TELEGRAM_VERIFY_SSL", True)

# === SERVICIO DE CORREO ELECTRONICO (GMAIL) ===
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER)

PASSWORD_RESET_TIMEOUT_HOURS = _env_int("PASSWORD_RESET_TIMEOUT_HOURS", 24)
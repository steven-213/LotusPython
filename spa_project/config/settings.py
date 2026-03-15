"""
Django settings for the reorganized spa project.
"""

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"
try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(ENV_FILE)
except Exception:
    if ENV_FILE.exists():
        for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)

def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_list(name: str) -> list[str]:
    raw = os.getenv(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    raise RuntimeError("DJANGO_SECRET_KEY is required")

DEBUG = _env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = _env_list("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = _env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.sesiones.apps.SesionesConfig",
    "apps.inventario",
    "apps.ventas",
    "apps.citas",
    
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

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
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

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


def _database_from_parts():
    host = os.getenv("DB_HOST", "").strip()
    name = os.getenv("DB_NAME", "").strip()
    if not host or not name:
        return None
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": name,
        "USER": os.getenv("DB_USER", "").strip(),
        "PASSWORD": os.getenv("DB_PASSWORD", "").strip(),
        "HOST": host,
        "PORT": os.getenv("DB_PORT", "").strip() or "5432",
        "OPTIONS": {"sslmode": os.getenv("DB_SSLMODE", "require").strip() or "require"},
    }


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
database_from_parts = _database_from_parts()
if database_from_parts:
    DATABASES = {"default": database_from_parts}
elif DATABASE_URL:
    DATABASES = {"default": _database_from_url(DATABASE_URL)}
else:
    # Keep tests/makemigrations lightweight in sqlite, but let migrate target
    # the real configured database so schema is created where the app runs.
    commands_using_sqlite = {"test", "makemigrations"}

    if any(cmd in sys.argv for cmd in commands_using_sqlite):
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": BASE_DIR / "test_db.sqlite3",
            }
        }
    else:
        raise RuntimeError("Database configuration missing. Set DB_* or DATABASE_URL.")

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-co"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_CONFIRM_TOKEN = os.getenv("TELEGRAM_CONFIRM_TOKEN", "")
APP_BASE_URL = os.getenv("APP_BASE_URL", "")
TELEGRAM_VERIFY_SSL = _env_bool("TELEGRAM_VERIFY_SSL", True)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "")

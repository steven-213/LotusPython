from .settings import *  # noqa: F401,F403

# Use a simpler static file storage backend during tests to avoid
# ManifestStaticFilesStorage lookups when collectstatic is not run.
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"
STORAGES["staticfiles"]["BACKEND"] = "django.contrib.staticfiles.storage.StaticFilesStorage"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "test_db.sqlite3",
    }
}

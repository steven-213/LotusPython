from django.apps import AppConfig


class SesionesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.sesiones"
    label = "sesiones"

    def ready(self):
        # Registra las senales al cargar la app.
        from . import signals  # noqa: F401

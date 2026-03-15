from django.apps import apps as django_apps
from django.db.models.signals import post_migrate
from django.dispatch import receiver


@receiver(post_migrate, dispatch_uid="sesiones_crear_admin")
def crear_admin(sender, **kwargs):
    # Crea un usuario admin por defecto al aplicar migraciones de la app sesiones.
    if sender.label != "sesiones":
        return
    Usuario = django_apps.get_model("sesiones", "Usuario")
    if not Usuario.objects.filter(documento=12345).exists():
        Usuario.objects.create(
            documento=12345,
            nombre="Admin",
            apellido="Sistema",
            correo="admin@sistema.com",
            fecha_nacimiento="1990-01-01",
            clave="1234",
            rol="admin",
        )

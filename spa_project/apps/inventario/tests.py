from django.test import TestCase
from django.urls import reverse

from apps.sesiones.models import Usuario


class InventarioUrlsTest(TestCase):
    def setUp(self):
        usuario = Usuario.objects.create(
            documento=1,
            nombre="Admin",
            apellido="Inv",
            correo="admin@inv.com",
            fecha_nacimiento="1990-01-01",
            clave="1234",
            rol="admin",
        )
        session = self.client.session
        session["usuario_id"] = usuario.id
        session["usuario_rol"] = "admin"
        session.save()

    def test_reverse_and_view(self):
        self.assertEqual(reverse("inventario:producto_lista"), "/inventario/productos/")
        response = self.client.get(reverse("inventario:producto_lista"))
        self.assertEqual(response.status_code, 200)

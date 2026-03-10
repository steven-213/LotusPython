import json

from django.test import TestCase
from django.urls import reverse

from apps.sesiones.models import Usuario
from apps.ventas.models import Venta


class VentasViewsTest(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create(
            documento=200,
            nombre="Admin",
            apellido="Ventas",
            correo="admin@ventas.com",
            fecha_nacimiento="1990-01-01",
            clave="1234",
            rol="admin",
        )
        self.cliente = Usuario.objects.create(
            documento=201,
            nombre="Cliente",
            apellido="Uno",
            correo="cliente@test.com",
            fecha_nacimiento="1995-01-01",
            clave="1234",
            rol="cliente",
        )
        session = self.client.session
        session["usuario_id"] = self.admin.id
        session["usuario_rol"] = "admin"
        session.save()

    def test_ventas_lista_ok(self):
        response = self.client.get(reverse("ventas:venta_lista"))
        self.assertEqual(response.status_code, 200)

    def test_api_ventas_get_post(self):
        post = self.client.post(
            reverse("ventas:api_ventas"),
            data=json.dumps({"cliente_id": self.cliente.id, "total": "25000"}),
            content_type="application/json",
        )
        self.assertEqual(post.status_code, 201)
        get = self.client.get(reverse("ventas:api_ventas"))
        self.assertEqual(get.status_code, 200)
        self.assertGreaterEqual(len(get.json()), 1)

    def test_api_resumen(self):
        Venta.objects.create(cliente=self.cliente, total=100)
        response = self.client.get(reverse("ventas:api_resumen"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total_ventas"], 1)

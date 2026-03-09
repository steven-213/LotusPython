import json

from django.test import TestCase
from django.urls import reverse

from apps.citas.models import Servicio
from apps.sesiones.models import Usuario


class CitasViewsAndApiTest(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create(
            documento=300,
            nombre="Cliente",
            apellido="Cita",
            correo="cliente@cita.com",
            fecha_nacimiento="1998-01-01",
            clave="1234",
            rol="cliente",
        )
        self.servicio = Servicio.objects.create(nombre="Facial", precio=50000)

        session = self.client.session
        session["usuario_id"] = self.usuario.id
        session["usuario_rol"] = "cliente"
        session.save()

    def test_calendario_ok(self):
        response = self.client.get(reverse("citas:calendario"))
        self.assertEqual(response.status_code, 200)

    def test_api_eventos_get_post(self):
        post = self.client.post(
            reverse("citas:api_eventos"),
            data=json.dumps(
                {
                    "cliente_id": self.usuario.id,
                    "servicio_id": self.servicio.id,
                    "startDate": "2026-03-09T10:00:00Z",
                    "endDate": "2026-03-09T11:00:00Z",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(post.status_code, 201)
        get = self.client.get(reverse("citas:api_eventos"))
        self.assertEqual(get.status_code, 200)
        self.assertGreaterEqual(len(get.json()), 1)

from django.test import TestCase
from django.urls import reverse

from apps.sesiones.models import Usuario


class SesionesUrlsTest(TestCase):
    def test_reverse_urls(self):
        self.assertEqual(reverse("sesiones:login"), "/login/")
        self.assertEqual(reverse("sesiones:perfil"), "/perfil/")

    def test_login_page(self):
        response = self.client.get(reverse("sesiones:login"))
        self.assertEqual(response.status_code, 200)


class SesionesAuthFlowTest(TestCase):
    def setUp(self):
        Usuario.objects.update_or_create(
            documento=12345,
            defaults={
                "nombre": "Admin",
                "apellido": "Test",
                "correo": "admin@test.com",
                "fecha_nacimiento": "1990-01-01",
                "clave": "1234",
                "rol": "admin",
            },
        )

    def test_login_sets_session(self):
        response = self.client.post(
            reverse("sesiones:login"),
            {"documento": "12345", "clave": "1234"},
            follow=True,
        )
        self.assertIn("usuario_id", self.client.session)
        self.assertEqual(response.status_code, 200)

    def test_registro_duplicate_documento_shows_alert(self):
        response = self.client.post(
            reverse("sesiones:registro"),
            {
                "documento": "12345",
                "nombre": "Nuevo",
                "apellido": "Usuario",
                "correo": "nuevo@test.com",
                "fechaNacimiento": "1995-05-10",
                "clave": "abcd",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Ya existe una cuenta registrada con ese documento.",
        )
        self.assertContains(
            response,
            "Ese documento ya tiene una cuenta registrada.",
        )
        self.assertEqual(Usuario.objects.filter(documento=12345).count(), 1)

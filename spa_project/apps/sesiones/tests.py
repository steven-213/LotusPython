from django.contrib.auth.hashers import check_password
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from apps.inventario.models import Producto, Proveedor
from apps.sesiones.models import RecuperacionClave, RegistroPendiente, Usuario
from apps.ventas.models import (
    DetalleVenta,
    SolicitudDevolucionVenta,
    ValidacionVenta,
    Venta,
)


class SesionesUrlsTest(TestCase):
    def test_reverse_urls(self):
        self.assertEqual(reverse("sesiones:login"), "/login/")
        self.assertEqual(reverse("sesiones:perfil"), "/perfil/")
        self.assertEqual(reverse("sesiones:password_reset_request"), "/olvide-contrasena/")

    def test_login_page(self):
        response = self.client.get(reverse("sesiones:login"))
        self.assertEqual(response.status_code, 200)

    def test_robots_txt_expone_sitemap_y_rutas_privadas(self):
        response = self.client.get(reverse("robots_txt"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sitemap:")
        self.assertContains(response, "sitemap.xml")
        self.assertContains(response, "Disallow: /login/")
        self.assertContains(response, "Disallow: /inventario/productos/")

    def test_sitemap_incluye_paginas_publicas_principales(self):
        response = self.client.get(reverse("sitemap"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "http://testserver/")
        self.assertContains(response, "http://testserver/conocenos/")
        self.assertContains(response, "http://testserver/citas/catalogo/")
        self.assertContains(response, "http://testserver/inventario/catalogo/")


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
        self.assertIn("usuario_session_expires_at", self.client.session)
        self.assertEqual(response.status_code, 200)
        usuario = Usuario.objects.get(documento=12345)
        self.assertTrue(check_password("1234", usuario.clave))

    def test_sesion_vencida_redirige_a_login_y_limpia_el_estado(self):
        usuario = Usuario.objects.get(documento=12345)
        session = self.client.session
        session["usuario_id"] = usuario.id
        session["usuario_rol"] = usuario.rol
        session["usuario_nombre"] = f"{usuario.nombre} {usuario.apellido}".strip()
        session["usuario_session_started_at"] = int(timezone.now().timestamp()) - 7200
        session["usuario_session_expires_at"] = int(timezone.now().timestamp()) - 60
        session.save()

        response = self.client.get(reverse("sesiones:perfil"))

        self.assertRedirects(
            response,
            f"{reverse('sesiones:login')}?next={reverse('sesiones:perfil')}&reason=session_expired",
            fetch_redirect_response=False,
        )
        self.assertNotIn("usuario_id", self.client.session)

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

    def test_registro_duplicate_correo_shows_alert(self):
        response = self.client.post(
            reverse("sesiones:registro"),
            {
                "documento": "54321",
                "nombre": "Nuevo",
                "apellido": "Correo",
                "correo": "ADMIN@test.com",
                "fechaNacimiento": "1995-05-10",
                "clave": "abcd",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Ya existe una cuenta registrada con ese correo.",
        )
        self.assertContains(
            response,
            "Ese correo ya tiene una cuenta registrada.",
        )
        self.assertEqual(Usuario.objects.filter(correo__iexact="admin@test.com").count(), 1)

    def test_registro_requires_email_code_before_creating_user(self):
        response = self.client.post(
            reverse("sesiones:registro"),
            {
                "documento": "54321",
                "nombre": "Nuevo",
                "apellido": "Cliente",
                "correo": "nuevo@test.com",
                "fechaNacimiento": "1995-05-10",
                "clave": "abcd1234",
            },
        )

        pending_registration = RegistroPendiente.objects.get(correo="nuevo@test.com")

        self.assertRedirects(
            response,
            reverse("sesiones:registro_verificar", args=[pending_registration.token]),
        )
        self.assertFalse(Usuario.objects.filter(correo="nuevo@test.com").exists())
        self.assertEqual(len(mail.outbox), 1)

        verification_code = self._extract_code(mail.outbox[0].body)
        verification_response = self.client.post(
            reverse("sesiones:registro_verificar", args=[pending_registration.token]),
            {"codigo": verification_code},
        )

        self.assertRedirects(verification_response, reverse("sesiones:login"))
        usuario = Usuario.objects.get(correo="nuevo@test.com")
        self.assertTrue(check_password("abcd1234", usuario.clave))
        self.assertFalse(RegistroPendiente.objects.filter(pk=pending_registration.pk).exists())

    def test_password_reset_updates_password_after_code_validation(self):
        response = self.client.post(
            reverse("sesiones:password_reset_request"),
            {"documento": "12345", "correo": "admin@test.com"},
        )

        password_reset = RecuperacionClave.objects.get(usuario__documento=12345)

        self.assertRedirects(
            response,
            reverse("sesiones:password_reset_confirm", args=[password_reset.token]),
        )
        self.assertEqual(len(mail.outbox), 1)

        verification_code = self._extract_code(mail.outbox[0].body)
        confirm_response = self.client.post(
            reverse("sesiones:password_reset_confirm", args=[password_reset.token]),
            {
                "codigo": verification_code,
                "clave": "nueva1234",
                "confirmar_clave": "nueva1234",
            },
        )

        self.assertRedirects(confirm_response, reverse("sesiones:login"))
        usuario = Usuario.objects.get(documento=12345)
        self.assertTrue(check_password("nueva1234", usuario.clave))
        self.assertFalse(RecuperacionClave.objects.filter(pk=password_reset.pk).exists())

    @staticmethod
    def _extract_code(message_body):
        for line in message_body.splitlines():
            if "codigo" in line.lower() and ":" in line:
                return line.split(":", 1)[1].strip()
        raise AssertionError("No se encontro el codigo en el correo enviado.")


class PerfilClienteTest(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create(
            documento=54321,
            nombre="Cliente",
            apellido="Perfil",
            correo="cliente@perfil.com",
            fecha_nacimiento="1996-04-12",
            clave="1234",
            rol="cliente",
        )
        proveedor = Proveedor.objects.create(
            nombre="Proveedor Perfil",
            nit="900111222",
        )
        producto = Producto.objects.create(
            nombre="Crema corporal",
            proveedor=proveedor,
            precio_compra=10000,
            precio_venta=18000,
            impuesto=19,
            margen_ganancia=20,
        )
        venta = Venta.objects.create(cliente=self.usuario, total=36000)
        detalle = DetalleVenta.objects.create(
            venta=venta,
            producto=producto,
            cantidad=2,
            precio_unitario=18000,
        )
        ValidacionVenta.objects.create(
            venta=venta,
            cliente=self.usuario,
            metodo_pago="transferencia",
            referencia_pago="WEB-1",
            monto=36000,
            estado="comprado",
            observaciones="Compra de prueba",
        )
        SolicitudDevolucionVenta.objects.create(
            detalle_venta=detalle,
            cliente=self.usuario,
            cantidad=1,
            motivo="El producto no era lo esperado.",
            estado=SolicitudDevolucionVenta.ESTADO_APROBADA,
        )

        session = self.client.session
        session["usuario_id"] = self.usuario.id
        session["usuario_rol"] = "cliente"
        session["usuario_nombre"] = f"{self.usuario.nombre} {self.usuario.apellido}"
        session.save()

    def test_perfil_muestra_estado_devolucion_en_compra_reciente(self):
        response = self.client.get(reverse("sesiones:perfil"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Devuelta parcial")
        self.assertContains(response, "Solicitud #")
        self.assertEqual(
            response.context["validaciones_recientes"][0]["estado_devolucion"]["label"],
            "Devuelta parcial",
        )

from django.test import TestCase
from django.urls import reverse
from apps.inventario.models import Producto, Proveedor
from apps.sesiones.models import Usuario
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

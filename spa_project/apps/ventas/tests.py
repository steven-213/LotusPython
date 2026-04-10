import json
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.inventario.models import Producto, Proveedor
from apps.inventario.services import obtener_stock_disponible
from apps.sesiones.models import Usuario
from apps.ventas import telegram_notifier
from apps.ventas.models import (
    DetalleVenta,
    SolicitudDevolucionVenta,
    ValidacionVenta,
    Venta,
)


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
        self.proveedor = Proveedor.objects.create(
            nombre="Proveedor Test",
            nit="900123456",
        )
        self.producto = Producto.objects.create(
            nombre="Aceite relajante",
            descripcion="Producto de prueba",
            proveedor=self.proveedor,
            precio_compra=Decimal("10000"),
            precio_venta=Decimal("15000"),
            impuesto=Decimal("19"),
            margen_ganancia=Decimal("20"),
        )
        self.set_admin_session()

    def set_admin_session(self):
        session = self.client.session
        session["usuario_id"] = self.admin.id
        session["usuario_rol"] = "admin"
        session.save()

    def set_client_session(self):
        session = self.client.session
        session["usuario_id"] = self.cliente.id
        session["usuario_rol"] = "cliente"
        session.save()

    def crear_compra_confirmada(self, *, cantidad=3, precio_unitario="15000"):
        precio_unitario = Decimal(precio_unitario)
        venta = Venta.objects.create(
            cliente=self.cliente,
            total=precio_unitario * cantidad,
        )
        detalle = DetalleVenta.objects.create(
            venta=venta,
            producto=self.producto,
            cantidad=cantidad,
            precio_unitario=precio_unitario,
        )
        ValidacionVenta.objects.create(
            venta=venta,
            cliente=self.cliente,
            metodo_pago="transferencia",
            referencia_pago=f"WEB-{venta.id}",
            monto=venta.total,
            estado="comprado",
            observaciones="Compra confirmada para pruebas.",
        )
        return venta, detalle

    def test_ventas_lista_ok(self):
        response = self.client.get(reverse("ventas:venta_lista"))
        self.assertEqual(response.status_code, 200)

    def test_venta_nueva_get_ok(self):
        response = self.client.get(reverse("ventas:venta_nueva"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Registrar nueva venta")

    def test_venta_nueva_post_crea_venta(self):
        response = self.client.post(
            reverse("ventas:venta_nueva"),
            data={"cliente_id": self.cliente.id, "total": "20.000"},
        )

        venta = Venta.objects.get()
        self.assertRedirects(response, reverse("ventas:venta_detalle", args=[venta.id]))
        self.assertEqual(venta.cliente, self.cliente)
        self.assertEqual(venta.total, Decimal("20000"))

    def test_venta_nueva_rechaza_total_negativo(self):
        response = self.client.post(
            reverse("ventas:venta_nueva"),
            data={"cliente_id": self.cliente.id, "total": "-20.000"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "El total de la venta debe ser mayor a cero.")
        self.assertEqual(Venta.objects.count(), 0)

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

    @override_settings(
        TELEGRAM_BOT_TOKEN="token-prueba",
        TELEGRAM_CHAT_ID='111,222',
        TELEGRAM_CHAT_IDS=[],
    )
    @patch("apps.ventas.telegram_notifier._enviar_mensaje_chat_telegram", return_value=True)
    def test_notificador_telegram_envia_a_todos_los_chats_configurados(self, send_mock):
        venta, _ = self.crear_compra_confirmada(cantidad=1)
        validacion = venta.validaciones.first()
        validacion.estado = "pendiente"
        validacion.save(update_fields=["estado"])

        enviado = telegram_notifier.notificar_compra_pendiente(venta, validacion)

        self.assertTrue(enviado)
        self.assertEqual(send_mock.call_count, 2)
        self.assertEqual(send_mock.call_args_list[0].args[1], "111")
        self.assertEqual(send_mock.call_args_list[1].args[1], "222")

    @patch("apps.ventas.views.devolucion_views.notificar_solicitud_devolucion", return_value=True)
    def test_cliente_puede_solicitar_devolucion_desde_compra_confirmada(self, notifier_mock):
        _, detalle = self.crear_compra_confirmada(cantidad=3)
        self.set_client_session()

        response = self.client.post(
            reverse("ventas:solicitar_devolucion", args=[detalle.id]),
            data={
                "cantidad": "2",
                "motivo": "El producto llego abierto y no lo puedo usar.",
            },
        )

        self.assertRedirects(response, reverse("sesiones:perfil"))
        solicitud = SolicitudDevolucionVenta.objects.get()
        self.assertEqual(solicitud.detalle_venta, detalle)
        self.assertEqual(solicitud.cliente, self.cliente)
        self.assertEqual(solicitud.cantidad, 2)
        self.assertEqual(solicitud.estado, SolicitudDevolucionVenta.ESTADO_PENDIENTE)
        notifier_mock.assert_called_once()

    @override_settings(TELEGRAM_CONFIRM_TOKEN="token-prueba")
    def test_aprobar_devolucion_telegram_reingresa_stock(self):
        _, detalle = self.crear_compra_confirmada(cantidad=4)
        solicitud = SolicitudDevolucionVenta.objects.create(
            detalle_venta=detalle,
            cliente=self.cliente,
            cantidad=2,
            motivo="El aroma no corresponde al solicitado.",
        )

        response = self.client.get(
            reverse("ventas:telegram_return_approve", args=[solicitud.id]),
            data={"token": "token-prueba"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Devolucion aprobada correctamente.")
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, SolicitudDevolucionVenta.ESTADO_APROBADA)
        self.assertEqual(obtener_stock_disponible(self.producto), 2)

    @override_settings(TELEGRAM_CONFIRM_TOKEN="token-prueba")
    def test_rechazar_devolucion_telegram_actualiza_estado(self):
        _, detalle = self.crear_compra_confirmada(cantidad=2)
        solicitud = SolicitudDevolucionVenta.objects.create(
            detalle_venta=detalle,
            cliente=self.cliente,
            cantidad=1,
            motivo="Prefiero cambiarlo por otro producto.",
        )

        response = self.client.get(
            reverse("ventas:telegram_return_reject", args=[solicitud.id]),
            data={"token": "token-prueba"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Devolucion rechazada correctamente.")
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, SolicitudDevolucionVenta.ESTADO_RECHAZADA)
        self.assertEqual(obtener_stock_disponible(self.producto), 0)

    def test_venta_lista_admin_muestra_resumen_devolucion_cliente(self):
        venta, detalle = self.crear_compra_confirmada(cantidad=3)
        SolicitudDevolucionVenta.objects.create(
            detalle_venta=detalle,
            cliente=self.cliente,
            cantidad=1,
            motivo="Deseo devolver una unidad.",
            estado=SolicitudDevolucionVenta.ESTADO_APROBADA,
            comentario_admin="Aprobada por el administrador.",
        )

        response = self.client.get(reverse("ventas:venta_lista"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Devolución Cliente")
        self.assertContains(response, "Devuelta parcial")
        self.assertContains(response, f"Devolucion aprobada de {self.producto.nombre}")
        self.assertContains(response, f"#{venta.id}")

    def test_venta_detalle_admin_muestra_devoluciones_del_cliente(self):
        venta, detalle = self.crear_compra_confirmada(cantidad=2)
        solicitud = SolicitudDevolucionVenta.objects.create(
            detalle_venta=detalle,
            cliente=self.cliente,
            cantidad=1,
            motivo="Llegó con el sello roto.",
            estado=SolicitudDevolucionVenta.ESTADO_PENDIENTE,
        )

        response = self.client.get(reverse("ventas:venta_detalle", args=[venta.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Devoluciones del Cliente")
        self.assertContains(response, "Estado de devolución cliente")
        self.assertContains(response, f"Solicitud #{solicitud.id}")
        self.assertContains(response, self.producto.nombre)
        self.assertContains(response, "Llegó con el sello roto.")

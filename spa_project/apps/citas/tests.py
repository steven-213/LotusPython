import json
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.citas.models import ClienteInvitado, PagoReserva, Profesional, Reserva, Servicio
from apps.citas.services import (
    cambiar_estado_reserva,
    configuracion_horario_reserva,
    crear_reserva,
    obtener_horas_disponibles_reserva,
)
from apps.inventario.models import Inventario, Producto, Proveedor
from apps.inventario.services import obtener_stock_disponible, registrar_ingreso
from apps.sesiones.models import Usuario


class CitasFlowTest(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create(
            documento=100,
            nombre="Admin",
            apellido="Spa",
            correo="admin@spa.com",
            fecha_nacimiento="1990-01-01",
            clave="1234",
            rol=Usuario.ROL_ADMIN,
        )
        self.cliente = Usuario.objects.create(
            documento=300,
            nombre="Cliente",
            apellido="Uno",
            correo="cliente1@spa.com",
            fecha_nacimiento="1998-01-01",
            clave="1234",
            rol=Usuario.ROL_CLIENTE,
        )
        self.otro_cliente = Usuario.objects.create(
            documento=301,
            nombre="Cliente",
            apellido="Dos",
            correo="cliente2@spa.com",
            fecha_nacimiento="1997-01-01",
            clave="1234",
            rol=Usuario.ROL_CLIENTE,
        )
        self.profesional = Profesional.objects.create(nombre="Laura")
        self.profesional_2 = Profesional.objects.create(nombre="Marta")
        self.servicio = Servicio.objects.create(
            nombre="Facial",
            precio=50000,
            profesional=self.profesional,
            duracion_minutos=60,
            activo=True,
        )
        self.servicio_2 = Servicio.objects.create(
            nombre="Masaje",
            precio=65000,
            profesional=self.profesional_2,
            duracion_minutos=60,
            activo=True,
        )

    def _future_start(self, days=2, hour=10):
        fecha = timezone.localtime(timezone.now() + timedelta(days=days))
        fecha = fecha.replace(hour=hour, minute=0, second=0, microsecond=0)
        while fecha.weekday() == 6:
            fecha += timedelta(days=1)
        return fecha

    def _future_input(self, days=2, hour=10, minute=0):
        return self._future_start(days=days, hour=hour).replace(minute=minute).strftime("%Y-%m-%dT%H:%M")

    def _future_weekday_start(self, weekday, hour, minute=0):
        fecha = timezone.localtime(timezone.now())
        dias = (weekday - fecha.weekday()) % 7
        if dias == 0:
            dias = 7
        return (fecha + timedelta(days=dias)).replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )

    def _force_session(self, usuario):
        session = self.client.session
        session["usuario_id"] = usuario.id
        session["usuario_rol"] = usuario.rol
        session.save()

    def _crear_reserva(self, *, cliente=None, servicio=None, fecha_inicio=None, pago=False):
        reserva, _ = crear_reserva(
            cliente=cliente or self.cliente,
            servicio=servicio or self.servicio,
            fecha_inicio=fecha_inicio or self._future_start(),
            notas="Prueba",
            origen=Reserva.ORIGEN_AUTENTICADO,
            actor=cliente or self.cliente,
            pago_data={
                "monto": (servicio or self.servicio).precio,
                "metodo_pago": PagoReserva.METODO_EFECTIVO,
                "referencia": "",
                "tipo": PagoReserva.TIPO_TOTAL,
            }
            if pago
            else None,
        )
        return reserva

    def test_guest_booking_requires_payment(self):
        response = self.client.post(
            reverse("citas:reserva_nueva"),
            {
                "documento": "888",
                "nombre": "Invitada",
                "apellido": "Prueba",
                "correo": "invitada@spa.com",
                "fecha_nacimiento": "1995-05-05",
                "servicio_id": self.servicio.id,
                "fecha_inicio": self._future_input(),
                "notas": "Sin pago",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Reserva.objects.count(), 0)
        self.assertFalse(Usuario.objects.filter(documento=888).exists())

    def test_guest_booking_with_payment_creates_confirmed_reservation(self):
        response = self.client.post(
            reverse("citas:reserva_nueva"),
            {
                "documento": "889",
                "nombre": "Invitada",
                "apellido": "Pago",
                "correo": "invitada.pago@spa.com",
                "fecha_nacimiento": "1994-04-04",
                "servicio_id": self.servicio.id,
                "fecha_inicio": self._future_input(),
                "metodo_pago": PagoReserva.METODO_NEQUI,
                "referencia_pago": "TX-INV-1",
            },
        )
        self.assertRedirects(response, reverse("citas:reserva_confirmada"))
        reserva = Reserva.objects.get()
        self.assertEqual(reserva.estado, Reserva.ESTADO_CONFIRMADA)
        self.assertEqual(reserva.origen_reserva, Reserva.ORIGEN_INVITADO)
        self.assertIsNone(reserva.cliente)
        self.assertIsNotNone(reserva.cliente_invitado)
        self.assertEqual(reserva.cliente_invitado.documento, 889)
        self.assertEqual(reserva.pagos.count(), 1)
        self.assertTrue(self.client.session.get("reserva_confirmada_token"))
        self.assertTrue(ClienteInvitado.objects.filter(documento=889).exists())
        self.assertFalse(Usuario.objects.filter(documento=889).exists())

    def test_guest_booking_does_not_block_future_registration(self):
        self.client.post(
            reverse("citas:reserva_nueva"),
            {
                "documento": "890",
                "nombre": "Invitada",
                "apellido": "Registro",
                "correo": "invitada.registro@spa.com",
                "fecha_nacimiento": "1993-03-03",
                "servicio_id": self.servicio.id,
                "fecha_inicio": self._future_input(days=3, hour=13),
                "metodo_pago": PagoReserva.METODO_TRANSFERENCIA,
                "referencia_pago": "TX-INV-REG",
            },
        )

        response = self.client.post(
            reverse("sesiones:registro"),
            {
                "documento": "890",
                "nombre": "Cuenta",
                "apellido": "Real",
                "correo": "cuenta.real@spa.com",
                "fecha_nacimiento": "1993-03-03",
                "clave": "secreta",
                "rol": Usuario.ROL_CLIENTE,
            },
        )

        self.assertRedirects(response, reverse("sesiones:login"))
        self.assertTrue(ClienteInvitado.objects.filter(documento=890).exists())
        self.assertTrue(Usuario.objects.filter(documento=890).exists())

    def test_authenticated_booking_without_payment_is_programada(self):
        self._force_session(self.cliente)
        response = self.client.post(
            reverse("citas:reserva_nueva"),
            {
                "servicio_id": self.servicio.id,
                "fecha_inicio": self._future_input(days=3, hour=11),
                "notas": "Pago presencial",
            },
        )
        reserva = Reserva.objects.get()
        self.assertRedirects(response, reverse("citas:reserva_detalle", kwargs={"reserva_id": reserva.id}))
        self.assertEqual(reserva.estado, Reserva.ESTADO_PROGRAMADA)
        self.assertEqual(reserva.pagos.count(), 0)

    def test_booking_form_uses_custom_datepicker_with_sundays_disabled(self):
        response = self.client.get(reverse("citas:reserva_nueva"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "flatpickr@4.6.13/dist/flatpickr.min.js")
        self.assertContains(response, "date.getDay() === 0")

    def test_authenticated_booking_accepts_separate_date_and_time_fields(self):
        self._force_session(self.cliente)
        fecha = self._future_start(days=3, hour=11)
        response = self.client.post(
            reverse("citas:reserva_nueva"),
            {
                "servicio_id": self.servicio.id,
                "fecha_reserva": fecha.strftime("%Y-%m-%d"),
                "hora_reserva": fecha.strftime("%H:%M"),
                "notas": "Campos separados",
            },
        )
        reserva = Reserva.objects.get()
        self.assertRedirects(response, reverse("citas:reserva_detalle", kwargs={"reserva_id": reserva.id}))
        self.assertEqual(reserva.fecha_inicio, fecha)
        self.assertEqual(reserva.estado, Reserva.ESTADO_PROGRAMADA)

    def test_authenticated_booking_with_payment_is_confirmada(self):
        self._force_session(self.cliente)
        response = self.client.post(
            reverse("citas:reserva_nueva"),
            {
                "servicio_id": self.servicio.id,
                "fecha_inicio": self._future_input(days=4, hour=12),
                "notas": "Pago ahora",
                "pagar_ahora": "1",
                "metodo_pago": PagoReserva.METODO_TARJETA,
                "referencia_pago": "CARD-1",
            },
        )
        reserva = Reserva.objects.get()
        self.assertRedirects(response, reverse("citas:reserva_detalle", kwargs={"reserva_id": reserva.id}))
        self.assertEqual(reserva.estado, Reserva.ESTADO_CONFIRMADA)
        self.assertEqual(reserva.pagos.count(), 1)

    def test_same_professional_overlap_is_rejected(self):
        fecha = self._future_weekday_start(0, 10)
        self._crear_reserva(cliente=self.cliente, fecha_inicio=fecha)

        with self.assertRaises(ValidationError):
            crear_reserva(
                cliente=self.otro_cliente,
                servicio=self.servicio,
                fecha_inicio=fecha,
                notas="Cruce",
                origen=Reserva.ORIGEN_AUTENTICADO,
                actor=self.otro_cliente,
                pago_data=None,
            )

    def test_different_professional_same_time_is_allowed(self):
        fecha = self._future_weekday_start(1, 10)
        self._crear_reserva(cliente=self.cliente, fecha_inicio=fecha)
        reserva = self._crear_reserva(cliente=self.otro_cliente, servicio=self.servicio_2, fecha_inicio=fecha)
        self.assertEqual(reserva.servicio_id, self.servicio_2.id)
        self.assertEqual(Reserva.objects.count(), 2)

    def test_rejects_appointment_at_one_am(self):
        fecha = self._future_weekday_start(0, 1)

        with self.assertRaises(ValidationError):
            crear_reserva(
                cliente=self.cliente,
                servicio=self.servicio,
                fecha_inicio=fecha,
                notas="Horario invalido",
                origen=Reserva.ORIGEN_AUTENTICADO,
                actor=self.cliente,
                pago_data=None,
            )

    def test_rejects_appointment_with_minutes_not_on_the_hour(self):
        fecha = self._future_weekday_start(0, 10, 30)

        with self.assertRaisesMessage(ValidationError, "horas exactas"):
            crear_reserva(
                cliente=self.cliente,
                servicio=self.servicio,
                fecha_inicio=fecha,
                notas="Horario con minutos",
                origen=Reserva.ORIGEN_AUTENTICADO,
                actor=self.cliente,
                pago_data=None,
            )

    def test_rejects_service_that_exceeds_closing_time(self):
        self.servicio.duracion_minutos = 120
        self.servicio.save(update_fields=["duracion_minutos"])
        fecha = self._future_weekday_start(0, 17)

        with self.assertRaises(ValidationError):
            crear_reserva(
                cliente=self.cliente,
                servicio=self.servicio,
                fecha_inicio=fecha,
                notas="Se pasa del cierre",
                origen=Reserva.ORIGEN_AUTENTICADO,
                actor=self.cliente,
                pago_data=None,
            )

    def test_schedule_configuration_matches_frontend_rules(self):
        configuracion = configuracion_horario_reserva()
        self.assertEqual(configuracion["intervalo_minutos"], 15)
        self.assertIsNone(configuracion["dias"][0])
        self.assertEqual(configuracion["dias"][1]["apertura"], "10:00")
        self.assertEqual(configuracion["dias"][1]["cierre"], "18:00")
        self.assertEqual(configuracion["dias"][6]["cierre"], "20:00")

    def test_available_hours_skip_existing_reservations(self):
        fecha = self._future_weekday_start(0, 10)
        self._crear_reserva(cliente=self.cliente, fecha_inicio=fecha)

        horas = obtener_horas_disponibles_reserva(
            servicio=self.servicio,
            fecha_reserva=fecha.date(),
        )

        self.assertNotIn("10:00", horas)
        self.assertNotIn("10:15", horas)
        self.assertNotIn("10:30", horas)
        self.assertNotIn("10:45", horas)
        self.assertIn("11:00", horas)

    def test_public_availability_api_can_exclude_current_reservation(self):
        reserva = self._crear_reserva(cliente=self.cliente, fecha_inicio=self._future_weekday_start(1, 10))

        response = self.client.get(
            reverse("citas:api_disponibilidad"),
            {
                "servicio_id": self.servicio.id,
                "fecha": reserva.fecha_inicio.date().isoformat(),
                "exclude_reserva_id": reserva.id,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("10:00", payload["horas_disponibles"])

    def test_client_cannot_view_other_user_reservation(self):
        reserva = self._crear_reserva(cliente=self.otro_cliente, fecha_inicio=self._future_start(days=7, hour=14))
        self._force_session(self.cliente)
        response = self.client.get(reverse("citas:reserva_detalle", kwargs={"reserva_id": reserva.id}))
        self.assertEqual(response.status_code, 404)

    def test_api_post_ignores_cliente_id_for_non_admin(self):
        self._force_session(self.cliente)
        response = self.client.post(
            reverse("citas:api_eventos"),
            data=json.dumps(
                {
                    "cliente_id": self.otro_cliente.id,
                    "servicio_id": self.servicio.id,
                    "start": self._future_start(days=8, hour=10).isoformat(),
                    "notas": "API segura",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        reserva = Reserva.objects.get()
        self.assertEqual(reserva.cliente_id, self.cliente.id)

    def test_authenticated_booking_with_minutes_is_rejected(self):
        self._force_session(self.cliente)
        response = self.client.post(
            reverse("citas:reserva_nueva"),
            {
                "servicio_id": self.servicio.id,
                "fecha_inicio": self._future_input(days=5, hour=10, minute=30),
                "notas": "Horario con minutos",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Reserva.objects.count(), 0)

    def test_booking_form_limits_input_to_hours(self):
        response = self.client.get(reverse("citas:reserva_nueva"))

        self.assertContains(response, 'step="3600"', html=False)
        self.assertContains(response, "Solo se aceptan horas exactas dentro del horario del spa.")

    def test_admin_can_mark_no_show_and_history_is_recorded(self):
        reserva = self._crear_reserva(cliente=self.cliente, fecha_inicio=self._future_start(days=9, hour=10))
        self._force_session(self.admin)
        response = self.client.post(reverse("citas:reserva_no_asistio", kwargs={"reserva_id": reserva.id}))
        self.assertRedirects(response, reverse("citas:calendario"))
        reserva.refresh_from_db()
        self.assertEqual(reserva.estado, Reserva.ESTADO_NO_ASISTIO)
        self.assertTrue(reserva.historial_estados.filter(estado_nuevo=Reserva.ESTADO_NO_ASISTIO).exists())

    def test_admin_can_register_products_from_reservation(self):
        reserva = self._crear_reserva(cliente=self.cliente, fecha_inicio=self._future_weekday_start(1, 11))
        proveedor = Proveedor.objects.create(nombre="Proveedor Spa", nit="900100100")
        producto = Producto.objects.create(
            nombre="Serum Premium",
            proveedor=proveedor,
            precio_compra=20000,
            precio_venta=35000,
            impuesto=19,
            margen_ganancia=20,
            activo=True,
        )
        registrar_ingreso(producto, 5, lote="TEST-CITA")

        self._force_session(self.admin)
        response = self.client.post(
            reverse("citas:reserva_registrar_pago", kwargs={"reserva_id": reserva.id}),
            {
                "monto": str(self.servicio.precio),
                "tipo_pago": PagoReserva.TIPO_TOTAL,
                "metodo_pago": PagoReserva.METODO_EFECTIVO,
                "referencia_pago": "FACTURA-CITA-1",
                "producto_id[]": [str(producto.id)],
                "cantidad_producto[]": ["2"],
            },
        )

        self.assertRedirects(response, reverse("citas:calendario"))
        reserva.refresh_from_db()
        self.assertEqual(reserva.pagos.count(), 1)
        self.assertEqual(reserva.estado, Reserva.ESTADO_CONFIRMADA)
        self.assertIsNotNone(reserva.venta_asociada_segura)
        self.assertEqual(reserva.venta_asociada_segura.detalles.count(), 1)
        self.assertEqual(reserva.venta_asociada_segura.total, producto.precio_venta * 2)
        self.assertEqual(obtener_stock_disponible(producto), 3)

    def test_dashboard_shows_selected_product_price_summary(self):
        reserva = self._crear_reserva(cliente=self.cliente, fecha_inicio=self._future_weekday_start(2, 11))
        proveedor = Proveedor.objects.create(nombre="Proveedor Visual", nit="900100101")
        producto = Producto.objects.create(
            nombre="Crema Hidratante",
            proveedor=proveedor,
            precio_compra=18000,
            precio_venta=32000,
            impuesto=19,
            margen_ganancia=20,
            activo=True,
        )
        registrar_ingreso(producto, 4, lote="TEST-VISUAL")

        self._force_session(self.admin)
        response = self.client.get(reverse("citas:calendario"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Precio unitario")
        self.assertContains(response, 'data-product-price-label')
        self.assertContains(response, 'data-price="32000')

    def test_dashboard_uses_inventory_price_when_product_price_is_zero(self):
        self._crear_reserva(cliente=self.cliente, fecha_inicio=self._future_weekday_start(3, 11))
        proveedor = Proveedor.objects.create(nombre="Proveedor Precio", nit="900100102")
        producto = Producto.objects.create(
            nombre="Crema Precio Inventario",
            proveedor=proveedor,
            precio_compra=15000,
            precio_venta=0,
            impuesto=19,
            margen_ganancia=20,
            activo=True,
        )
        Inventario.objects.create(
            producto=producto,
            lote="TEST-PRECIO",
            stock=6,
            precio_venta=28000,
        )

        self._force_session(self.admin)
        response = self.client.get(reverse("citas:calendario"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-name="Crema Precio Inventario"')
        self.assertContains(response, 'data-price="28000')

    def test_cannot_finalize_without_being_in_process(self):
        reserva = self._crear_reserva(cliente=self.cliente, fecha_inicio=self._future_start(days=10, hour=16))
        with self.assertRaises(ValidationError):
            cambiar_estado_reserva(
                reserva=reserva,
                nuevo_estado=Reserva.ESTADO_FINALIZADA,
                actor=self.admin,
                observacion="Intento invalido",
            )

    def test_owner_can_download_receipt_pdf(self):
        reserva = self._crear_reserva(
            cliente=self.cliente,
            fecha_inicio=self._future_start(days=11, hour=15),
            pago=True,
        )
        pago = reserva.pagos.first()
        self._force_session(self.cliente)
        response = self.client.get(reverse("citas:comprobante_pago_pdf", kwargs={"pago_id": pago.id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_servicio_nuevo_rechaza_duplicado_para_misma_profesional(self):
        self._force_session(self.admin)

        response = self.client.post(
            reverse("citas:servicio_nuevo"),
            {
                "nombre": "facial",
                "descripcion": "Duplicado",
                "precio": "50.000",
                "duracion_minutos": "60",
                "profesional_id": str(self.profesional.id),
                "activo": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Ya existe un servicio con ese nombre para la profesional seleccionada.",
        )
        self.assertEqual(Servicio.objects.filter(nombre__iexact="Facial", profesional=self.profesional).count(), 1)

    def test_calendario_admin_redirige_a_login_sin_sesion(self):
        response = self.client.get(reverse("citas:calendario"))

        self.assertRedirects(
            response,
            f"{reverse('sesiones:login')}?next={reverse('citas:calendario')}",
            fetch_redirect_response=False,
        )

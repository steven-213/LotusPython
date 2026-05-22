import json
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.common.currency import format_money
from apps.citas.models import ClienteInvitado, PagoReserva, Profesional, Reserva, Servicio
from apps.citas.services import (
    cambiar_estado_reserva,
    configuracion_horario_reserva,
    crear_reserva,
    obtener_horas_disponibles_reserva,
    registrar_pago,
    resumen_dashboard_admin,
)
from apps.inventario.models import Inventario, Producto, Proveedor
from apps.inventario.services import obtener_stock_disponible, registrar_ingreso
from apps.sesiones.models import Usuario
from apps.ventas.services import registrar_venta_desde_reserva


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
                "clave": "secreta8",
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

    def test_booking_form_uses_custom_datepicker_with_sundays_disabled_and_blocks_past_dates(self):
        response = self.client.get(reverse("citas:reserva_nueva"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "flatpickr@4.6.13/dist/flatpickr.min.js")
        self.assertContains(response, 'minDate: "today"')
        self.assertContains(response, "date.getDay() === 0")
        self.assertNotContains(response, "date.getDay() === 6")

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

    def test_admin_can_reassign_professional_from_reservation_detail(self):
        reserva = self._crear_reserva(cliente=self.cliente, fecha_inicio=self._future_weekday_start(2, 10))
        self._force_session(self.admin)

        detail_response = self.client.get(reverse("citas:reserva_detalle", kwargs={"reserva_id": reserva.id}))
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "Reasignar profesional")

        response = self.client.post(
            reverse("citas:reserva_actualizar_profesional", kwargs={"reserva_id": reserva.id}),
            {
                "profesional_id": str(self.profesional_2.id),
            },
        )

        self.assertRedirects(response, reverse("citas:reserva_detalle", kwargs={"reserva_id": reserva.id}))
        reserva.refresh_from_db()
        self.assertEqual(reserva.profesional_id, self.profesional_2.id)
        self.assertTrue(
            reserva.historial_estados.filter(observacion__icontains="Profesional reasignada a Marta").exists()
        )

    def test_admin_can_create_professional_from_reservation_detail(self):
        reserva = self._crear_reserva(cliente=self.cliente, fecha_inicio=self._future_weekday_start(3, 10))
        self._force_session(self.admin)

        response = self.client.post(
            reverse("citas:reserva_actualizar_profesional", kwargs={"reserva_id": reserva.id}),
            {
                "profesional_id": str(self.profesional.id),
                "profesional_nombre": "Andrea",
            },
        )

        self.assertRedirects(response, reverse("citas:reserva_detalle", kwargs={"reserva_id": reserva.id}))
        reserva.refresh_from_db()
        profesional_nueva = Profesional.objects.get(nombre="Andrea")
        self.assertEqual(reserva.profesional_id, profesional_nueva.id)
        self.assertTrue(profesional_nueva.activo)

    def test_admin_cannot_reassign_professional_to_conflicting_schedule(self):
        fecha = self._future_weekday_start(4, 10)
        reserva = self._crear_reserva(cliente=self.cliente, fecha_inicio=fecha)
        self._crear_reserva(cliente=self.otro_cliente, servicio=self.servicio_2, fecha_inicio=fecha)
        self._force_session(self.admin)

        response = self.client.post(
            reverse("citas:reserva_actualizar_profesional", kwargs={"reserva_id": reserva.id}),
            {
                "profesional_id": str(self.profesional_2.id),
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ya tiene una cita en ese horario")
        reserva.refresh_from_db()
        self.assertEqual(reserva.profesional_id, self.profesional.id)

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

    def test_rejects_appointment_with_minutes_outside_15_minute_interval(self):
        fecha = self._future_weekday_start(0, 10, 7)

        with self.assertRaisesMessage(ValidationError, "15 minutos"):
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

    def test_available_hours_include_quarter_hour_slots(self):
        fecha = self._future_weekday_start(0, 10)

        horas = obtener_horas_disponibles_reserva(
            servicio=self.servicio,
            fecha_reserva=fecha.date(),
        )

        self.assertIn("10:00", horas)
        self.assertIn("10:15", horas)
        self.assertIn("10:30", horas)
        self.assertIn("10:45", horas)

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

    def test_public_availability_api_rejects_past_dates(self):
        response = self.client.get(
            reverse("citas:api_disponibilidad"),
            {
                "servicio_id": self.servicio.id,
                "fecha": (timezone.localdate() - timedelta(days=1)).isoformat(),
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"],
            "No hay horarios disponibles para fechas anteriores a hoy.",
        )

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

    def test_authenticated_booking_with_minutes_outside_15_minute_interval_is_rejected(self):
        self._force_session(self.cliente)
        response = self.client.post(
            reverse("citas:reserva_nueva"),
            {
                "servicio_id": self.servicio.id,
                "fecha_inicio": self._future_input(days=5, hour=10, minute=17),
                "notas": "Horario con minutos",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Reserva.objects.count(), 0)

    def test_booking_form_mentions_quarter_hour_availability(self):
        response = self.client.get(reverse("citas:reserva_nueva"))

        self.assertContains(response, "mostramos intervalos de 15 minutos")

    def test_dashboard_admin_root_is_available(self):
        reserva = self._crear_reserva(cliente=self.cliente, fecha_inicio=self._future_start(days=6, hour=11))
        self._force_session(self.admin)

        response = self.client.get(reverse("citas:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ingresos facturados")
        self.assertNotContains(response, "Dashboard admin")
        self.assertContains(response, f"{reserva.cliente_nombre_completo}")
        self.assertNotContains(response, "Registrar pago o cancelar")
        self.assertNotContains(response, 'id="calendar"', html=False)

    def test_dashboard_atajo_pendientes_filtra_reservas(self):
        pendiente = self._crear_reserva(cliente=self.cliente, fecha_inicio=self._future_start(days=7, hour=10))
        finalizada = self._crear_reserva(
            cliente=self.otro_cliente,
            fecha_inicio=self._future_start(days=8, hour=11),
            pago=True,
        )
        cambiar_estado_reserva(
            reserva=finalizada,
            nuevo_estado=Reserva.ESTADO_EN_PROCESO,
            actor=self.admin,
            observacion="Prueba orden",
        )
        cambiar_estado_reserva(
            reserva=finalizada,
            nuevo_estado=Reserva.ESTADO_FINALIZADA,
            actor=self.admin,
            observacion="Prueba orden",
        )
        self._force_session(self.admin)

        response = self.client.get(reverse("citas:dashboard"), {"atajo": "pendientes"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"{pendiente.cliente_nombre_completo}")
        self.assertNotContains(response, f"{finalizada.cliente_nombre_completo}")

    def test_dashboard_orders_in_process_before_pending_and_finished(self):
        pendiente = self._crear_reserva(
            cliente=self.cliente,
            fecha_inicio=self._future_weekday_start(1, 10),
        )
        en_proceso = self._crear_reserva(
            cliente=self.otro_cliente,
            fecha_inicio=self._future_weekday_start(2, 11),
        )
        finalizada = self._crear_reserva(
            cliente=self.cliente,
            servicio=self.servicio_2,
            fecha_inicio=self._future_weekday_start(3, 12),
            pago=True,
        )
        cambiar_estado_reserva(
            reserva=en_proceso,
            nuevo_estado=Reserva.ESTADO_EN_PROCESO,
            actor=self.admin,
            observacion="Prueba orden",
        )
        cambiar_estado_reserva(
            reserva=finalizada,
            nuevo_estado=Reserva.ESTADO_EN_PROCESO,
            actor=self.admin,
            observacion="Prueba orden",
        )
        cambiar_estado_reserva(
            reserva=finalizada,
            nuevo_estado=Reserva.ESTADO_FINALIZADA,
            actor=self.admin,
            observacion="Prueba orden",
        )
        self._force_session(self.admin)

        response = self.client.get(reverse("citas:dashboard"))

        self.assertEqual(response.status_code, 200)
        ids = [reserva.id for reserva in response.context["reservas"][:3]]
        self.assertEqual(ids, [en_proceso.id, pendiente.id, finalizada.id])

    def test_admin_can_mark_no_show_and_history_is_recorded(self):
        reserva = self._crear_reserva(cliente=self.cliente, fecha_inicio=self._future_start(days=9, hour=10))
        self._force_session(self.admin)
        response = self.client.post(reverse("citas:reserva_no_asistio", kwargs={"reserva_id": reserva.id}))
        self.assertRedirects(response, reverse("citas:almanaque"))
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

    def test_total_payment_must_match_pending_balance_exactly(self):
        reserva = self._crear_reserva(cliente=self.cliente, fecha_inicio=self._future_weekday_start(2, 11))

        with self.assertRaisesMessage(ValidationError, "exactamente el saldo pendiente"):
            registrar_pago(
                reserva=reserva,
                monto=Decimal("40000"),
                metodo_pago=PagoReserva.METODO_EFECTIVO,
                tipo=PagoReserva.TIPO_TOTAL,
                actor=self.admin,
            )

        with self.assertRaisesMessage(ValidationError, "supera el saldo pendiente"):
            registrar_pago(
                reserva=reserva,
                monto=Decimal("60000"),
                metodo_pago=PagoReserva.METODO_EFECTIVO,
                tipo=PagoReserva.TIPO_TOTAL,
                actor=self.admin,
            )

    def test_anticipo_must_be_lower_than_pending_balance(self):
        reserva = self._crear_reserva(cliente=self.cliente, fecha_inicio=self._future_weekday_start(3, 11))

        pago = registrar_pago(
            reserva=reserva,
            monto=Decimal("20000"),
            metodo_pago=PagoReserva.METODO_TRANSFERENCIA,
            tipo=PagoReserva.TIPO_ANTICIPO,
            actor=self.admin,
        )

        reserva.refresh_from_db()
        self.assertEqual(pago.tipo, PagoReserva.TIPO_ANTICIPO)
        self.assertEqual(reserva.total_pagado, Decimal("20000"))
        self.assertEqual(reserva.saldo_pendiente, Decimal("30000"))
        self.assertFalse(reserva.esta_pagada)

        with self.assertRaisesMessage(ValidationError, "menor al saldo pendiente"):
            registrar_pago(
                reserva=reserva,
                monto=Decimal("30000"),
                metodo_pago=PagoReserva.METODO_EFECTIVO,
                tipo=PagoReserva.TIPO_ANTICIPO,
                actor=self.admin,
            )

    def test_client_detail_payment_uses_remaining_balance(self):
        reserva = self._crear_reserva(cliente=self.cliente, fecha_inicio=self._future_weekday_start(4, 11))
        registrar_pago(
            reserva=reserva,
            monto=Decimal("20000"),
            metodo_pago=PagoReserva.METODO_TRANSFERENCIA,
            tipo=PagoReserva.TIPO_ANTICIPO,
            actor=self.admin,
        )

        self._force_session(self.cliente)
        response = self.client.post(
            reverse("citas:reserva_registrar_pago", kwargs={"reserva_id": reserva.id}),
            {
                "metodo_pago": PagoReserva.METODO_EFECTIVO,
                "referencia_pago": "PAGO-SALDO",
            },
        )

        self.assertRedirects(response, reverse("citas:reserva_detalle", kwargs={"reserva_id": reserva.id}))
        reserva.refresh_from_db()
        self.assertEqual(reserva.total_pagado, self.servicio.precio)
        self.assertEqual(reserva.saldo_pendiente, Decimal("0"))
        self.assertEqual(reserva.ultimo_pago_confirmado.monto, Decimal("30000"))

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
        response = self.client.get(reverse("citas:reserva_detalle", kwargs={"reserva_id": reserva.id}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Precio unitario")
        self.assertContains(response, 'data-product-price-label')
        self.assertContains(response, 'data-price="32000')

    def test_dashboard_uses_inventory_price_when_product_price_is_zero(self):
        reserva = self._crear_reserva(cliente=self.cliente, fecha_inicio=self._future_weekday_start(3, 11))
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
        response = self.client.get(reverse("citas:reserva_detalle", kwargs={"reserva_id": reserva.id}))

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

    def test_cannot_finalize_reservation_with_pending_balance(self):
        reserva = self._crear_reserva(cliente=self.cliente, fecha_inicio=self._future_weekday_start(5, 11))
        cambiar_estado_reserva(
            reserva=reserva,
            nuevo_estado=Reserva.ESTADO_EN_PROCESO,
            actor=self.admin,
            observacion="Inicio de atencion",
        )
        registrar_pago(
            reserva=reserva,
            monto=Decimal("15000"),
            metodo_pago=PagoReserva.METODO_EFECTIVO,
            tipo=PagoReserva.TIPO_ANTICIPO,
            actor=self.admin,
        )

        with self.assertRaisesMessage(ValidationError, "saldo pendiente"):
            cambiar_estado_reserva(
                reserva=reserva,
                nuevo_estado=Reserva.ESTADO_FINALIZADA,
                actor=self.admin,
                observacion="Intento con anticipo",
            )

        reserva.refresh_from_db()
        self.assertEqual(reserva.estado, Reserva.ESTADO_EN_PROCESO)

    def test_detail_hides_finalize_action_while_balance_is_pending(self):
        reserva = self._crear_reserva(cliente=self.cliente, fecha_inicio=self._future_weekday_start(1, 12))
        cambiar_estado_reserva(
            reserva=reserva,
            nuevo_estado=Reserva.ESTADO_EN_PROCESO,
            actor=self.admin,
            observacion="Inicio de atencion",
        )
        registrar_pago(
            reserva=reserva,
            monto=Decimal("10000"),
            metodo_pago=PagoReserva.METODO_EFECTIVO,
            tipo=PagoReserva.TIPO_ANTICIPO,
            actor=self.admin,
        )

        self._force_session(self.admin)
        response = self.client.get(reverse("citas:reserva_detalle", kwargs={"reserva_id": reserva.id}))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Finalizar cita")
        self.assertContains(response, "Falta pago para finalizar")

    def test_admin_failed_payment_redirects_to_dashboard(self):
        reserva = self._crear_reserva(cliente=self.cliente, fecha_inicio=self._future_weekday_start(2, 12))
        self._force_session(self.admin)

        response = self.client.post(
            reverse("citas:reserva_registrar_pago", kwargs={"reserva_id": reserva.id}),
            {
                "monto": "40000",
                "tipo_pago": PagoReserva.TIPO_TOTAL,
                "metodo_pago": PagoReserva.METODO_EFECTIVO,
            },
        )

        self.assertRedirects(response, reverse("citas:dashboard"))

    def test_finalized_reservation_updates_factored_income_summary(self):
        reserva = self._crear_reserva(
            cliente=self.cliente,
            fecha_inicio=self._future_weekday_start(4, 12),
            pago=True,
        )
        cambiar_estado_reserva(
            reserva=reserva,
            nuevo_estado=Reserva.ESTADO_EN_PROCESO,
            actor=self.admin,
            observacion="Inicio de atencion",
        )
        cambiar_estado_reserva(
            reserva=reserva,
            nuevo_estado=Reserva.ESTADO_FINALIZADA,
            actor=self.admin,
            observacion="Cita cerrada",
        )

        resumen = resumen_dashboard_admin()

        self.assertEqual(resumen["ingresos_por_periodo"]["hoy"]["cantidad"], 1)
        self.assertEqual(
            resumen["ingresos_por_periodo"]["hoy"]["total_monto"],
            format_money(self.servicio.precio),
        )
        self.assertEqual(
            resumen["ingresos_por_periodo"]["hoy"]["servicios_monto"],
            format_money(self.servicio.precio),
        )
        self.assertEqual(
            resumen["ingresos_por_periodo"]["hoy"]["productos_monto"],
            format_money(Decimal("0")),
        )
        self.assertEqual(resumen["ingresos_por_periodo"]["todas"]["cantidad"], 1)

    def test_finalized_reservation_income_summary_includes_products(self):
        reserva = self._crear_reserva(
            cliente=self.cliente,
            fecha_inicio=self._future_weekday_start(5, 12),
            pago=True,
        )
        proveedor = Proveedor.objects.create(nombre="Proveedor KPI", nit="900100103")
        producto = Producto.objects.create(
            nombre="Aceite Relajante",
            proveedor=proveedor,
            precio_compra=12000,
            precio_venta=28000,
            impuesto=19,
            margen_ganancia=20,
            activo=True,
        )
        registrar_ingreso(producto, 3, lote="TEST-KPI")

        cambiar_estado_reserva(
            reserva=reserva,
            nuevo_estado=Reserva.ESTADO_EN_PROCESO,
            actor=self.admin,
            observacion="Inicio de atencion",
        )
        registrar_venta_desde_reserva(
            reserva=reserva,
            items=[
                {
                    "producto": producto,
                    "cantidad": 2,
                }
            ],
            metodo_pago=PagoReserva.METODO_EFECTIVO,
            referencia_pago="KPI-PRODUCTOS",
            validado_por=self.admin.id,
        )
        cambiar_estado_reserva(
            reserva=reserva,
            nuevo_estado=Reserva.ESTADO_FINALIZADA,
            actor=self.admin,
            observacion="Cita cerrada con productos",
        )

        resumen = resumen_dashboard_admin()
        total_esperado = self.servicio.precio + (producto.precio_venta * 2)

        self.assertEqual(
            resumen["ingresos_por_periodo"]["hoy"]["total_monto"],
            format_money(total_esperado),
        )
        self.assertEqual(
            resumen["ingresos_por_periodo"]["hoy"]["servicios_monto"],
            format_money(self.servicio.precio),
        )
        self.assertEqual(
            resumen["ingresos_por_periodo"]["hoy"]["productos_monto"],
            format_money(producto.precio_venta * 2),
        )
        self.assertEqual(resumen["ingresos_por_periodo"]["hoy"]["cantidad"], 1)

    def test_dashboard_shows_split_income_values(self):
        reserva = self._crear_reserva(
            cliente=self.cliente,
            fecha_inicio=self._future_weekday_start(0, 12),
            pago=True,
        )
        proveedor = Proveedor.objects.create(nombre="Proveedor Dashboard KPI", nit="900100104")
        producto = Producto.objects.create(
            nombre="Crema Dashboard",
            proveedor=proveedor,
            precio_compra=10000,
            precio_venta=25000,
            impuesto=19,
            margen_ganancia=20,
            activo=True,
        )
        registrar_ingreso(producto, 2, lote="TEST-DASHBOARD-KPI")
        cambiar_estado_reserva(
            reserva=reserva,
            nuevo_estado=Reserva.ESTADO_EN_PROCESO,
            actor=self.admin,
            observacion="Inicio de atencion",
        )
        registrar_venta_desde_reserva(
            reserva=reserva,
            items=[{"producto": producto, "cantidad": 1}],
            metodo_pago=PagoReserva.METODO_EFECTIVO,
            referencia_pago="DASHBOARD-KPI",
            validado_por=self.admin.id,
        )
        cambiar_estado_reserva(
            reserva=reserva,
            nuevo_estado=Reserva.ESTADO_FINALIZADA,
            actor=self.admin,
            observacion="Cierre dashboard",
        )

        self._force_session(self.admin)
        response = self.client.get(reverse("citas:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Citas")
        self.assertContains(response, "Productos")
        self.assertContains(response, format_money(self.servicio.precio))
        self.assertContains(response, format_money(producto.precio_venta))

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
            "Ya existe un servicio con ese nombre.",
        )
        self.assertEqual(Servicio.objects.filter(nombre__iexact="Facial", profesional=self.profesional).count(), 1)

    def test_servicio_nuevo_rechaza_duplicado_aunque_sea_otra_profesional(self):
        self._force_session(self.admin)

        response = self.client.post(
            reverse("citas:servicio_nuevo"),
            {
                "nombre": "Facial",
                "descripcion": "Duplicado global",
                "precio": "55.000",
                "duracion_minutos": "60",
                "profesional_id": str(self.profesional_2.id),
                "activo": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ya existe un servicio con ese nombre.")
        self.assertEqual(Servicio.objects.filter(nombre__iexact="Facial").count(), 1)

    def test_servicio_nuevo_rechaza_duracion_menor_a_15_minutos(self):
        self._force_session(self.admin)

        response = self.client.post(
            reverse("citas:servicio_nuevo"),
            {
                "nombre": "Masaje corto",
                "descripcion": "Servicio invalido",
                "precio": "35.000",
                "duracion_minutos": "10",
                "profesional_id": str(self.profesional.id),
                "activo": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "La duracion del servicio debe ser mayor o igual a 15.")
        self.assertFalse(Servicio.objects.filter(nombre="Masaje corto").exists())

    def test_calendario_admin_redirige_a_login_sin_sesion(self):
        response = self.client.get(reverse("citas:calendario"))

        self.assertRedirects(
            response,
            f"{reverse('sesiones:login')}?next={reverse('citas:calendario')}",
            fetch_redirect_response=False,
        )

from datetime import date, time, timedelta
from decimal import Decimal, InvalidOperation
from django.core import signing
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.common.currency import parse_money
from apps.citas.models import ClienteInvitado, PagoReserva, Reserva, ReservaHistorialEstado, Servicio
from apps.sesiones.models import Usuario


ESTADOS_CONFLICTIVOS = {
    Reserva.ESTADO_PROGRAMADA,
    Reserva.ESTADO_CONFIRMADA,
    Reserva.ESTADO_EN_PROCESO,
}

TRANSICIONES_VALIDAS = {
    Reserva.ESTADO_PROGRAMADA: {
        Reserva.ESTADO_CONFIRMADA,
        Reserva.ESTADO_EN_PROCESO,
        Reserva.ESTADO_CANCELADA,
        Reserva.ESTADO_NO_ASISTIO,
    },
    Reserva.ESTADO_CONFIRMADA: {
        Reserva.ESTADO_EN_PROCESO,
        Reserva.ESTADO_CANCELADA,
        Reserva.ESTADO_NO_ASISTIO,
    },
    Reserva.ESTADO_EN_PROCESO: {
        Reserva.ESTADO_FINALIZADA,
        Reserva.ESTADO_CANCELADA,
    },
}

HORARIOS_ATENCION = {
    0: (time(hour=10, minute=0), time(hour=18, minute=0)),
    1: (time(hour=10, minute=0), time(hour=18, minute=0)),
    2: (time(hour=10, minute=0), time(hour=18, minute=0)),
    3: (time(hour=10, minute=0), time(hour=18, minute=0)),
    4: (time(hour=10, minute=0), time(hour=18, minute=0)),
    5: (time(hour=10, minute=0), time(hour=20, minute=0)),
}


def resumen_horario_atencion():
    return "Lunes a viernes de 10:00 AM a 6:00 PM. Sabados de 10:00 AM a 8:00 PM. Domingos sin atencion."


def obtener_horario_atencion(fecha_inicio):
    fecha_local = timezone.localtime(fecha_inicio)
    return HORARIOS_ATENCION.get(fecha_local.weekday())


def _formatear_horario(apertura, cierre):
    return f"{apertura.strftime('%I:%M %p')} - {cierre.strftime('%I:%M %p')}"


def validar_horario_reserva(*, fecha_inicio, fecha_fin):
    fecha_inicio_local = timezone.localtime(fecha_inicio)
    fecha_fin_local = timezone.localtime(fecha_fin)
    horario = obtener_horario_atencion(fecha_inicio)
    if not horario:
        raise ValidationError("No hay atencion disponible para la fecha seleccionada. Los domingos permanecemos cerrados.")

    if fecha_inicio_local.date() != fecha_fin_local.date():
        raise ValidationError("La cita debe iniciar y finalizar el mismo dia dentro del horario de atencion.")

    apertura, cierre = horario
    horario_legible = _formatear_horario(apertura, cierre)
    if fecha_inicio_local.time() < apertura or fecha_inicio_local.time() >= cierre:
        raise ValidationError(
            f"La hora de inicio esta fuera del horario de atencion. Horario permitido: {horario_legible}."
        )
    if fecha_fin_local.time() > cierre:
        raise ValidationError(
            f"La duracion del servicio supera la hora de cierre. Horario permitido: {horario_legible}."
        )


def calcular_fecha_fin(servicio: Servicio, fecha_inicio):
    return fecha_inicio + timedelta(minutes=servicio.duracion_minutos or 60)


def crear_o_reutilizar_cliente_invitado(*, documento, nombre, apellido, correo, fecha_nacimiento):
    documento_raw = str(documento or "").strip()
    nombre = (nombre or "").strip()
    apellido = (apellido or "").strip()
    correo = (correo or "").strip().lower()
    fecha_nacimiento_raw = str(fecha_nacimiento or "").strip()

    if not documento_raw or not nombre or not apellido or not correo or not fecha_nacimiento_raw:
        raise ValidationError("Debes completar todos los datos del cliente para reservar sin iniciar sesion.")

    try:
        documento = int(documento_raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError("El documento ingresado no es valido.") from exc

    try:
        fecha_nacimiento_valor = date.fromisoformat(fecha_nacimiento_raw)
    except ValueError as exc:
        raise ValidationError("La fecha de nacimiento no es valida.") from exc
    if fecha_nacimiento_valor > timezone.localdate():
        raise ValidationError("La fecha de nacimiento no puede estar en el futuro.")

    invitado = ClienteInvitado.objects.filter(documento=documento).first()
    if invitado:
        invitado.nombre = nombre
        invitado.apellido = apellido
        invitado.correo = correo
        invitado.fecha_nacimiento = fecha_nacimiento_valor
        invitado.save(update_fields=["nombre", "apellido", "correo", "fecha_nacimiento", "updated_at"])
        return invitado

    invitado = ClienteInvitado(
        documento=documento,
        nombre=nombre,
        apellido=apellido,
        correo=correo,
        fecha_nacimiento=fecha_nacimiento_valor,
    )
    invitado.full_clean()
    invitado.save()
    return invitado


def obtener_conflicto_reserva(*, servicio, fecha_inicio, fecha_fin, exclude_reserva_id=None):
    if not servicio.profesional_id:
        return None

    conflictos = Reserva.objects.select_related(
        "cliente", "cliente_invitado", "servicio", "servicio__profesional"
    ).filter(
        servicio__profesional=servicio.profesional,
        estado__in=ESTADOS_CONFLICTIVOS,
        fecha_inicio__lt=fecha_fin,
        fecha_fin__gt=fecha_inicio,
    )
    if exclude_reserva_id:
        conflictos = conflictos.exclude(id=exclude_reserva_id)
    return conflictos.first()


def validar_reserva(*, servicio, fecha_inicio, fecha_fin, exclude_reserva_id=None):
    ahora = timezone.now()
    if not servicio.activo:
        raise ValidationError("El servicio seleccionado no esta disponible.")
    if not servicio.profesional_id:
        raise ValidationError("El servicio no tiene una profesional asignada.")
    if fecha_inicio < ahora:
        raise ValidationError("No se pueden crear citas en el pasado.")
    if fecha_fin <= fecha_inicio:
        raise ValidationError("La fecha de fin debe ser posterior a la fecha de inicio.")
    validar_horario_reserva(fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)

    conflicto = obtener_conflicto_reserva(
        servicio=servicio,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        exclude_reserva_id=exclude_reserva_id,
    )
    if conflicto:
        raise ValidationError(f"La profesional ya tiene una cita en ese horario con {conflicto.cliente_nombre_completo}.")


def registrar_historial_estado(*, reserva, estado_anterior, estado_nuevo, usuario_actor=None, observacion=""):
    return ReservaHistorialEstado.objects.create(
        reserva=reserva,
        estado_anterior=estado_anterior or "",
        estado_nuevo=estado_nuevo,
        usuario_actor=usuario_actor,
        observacion=observacion or "",
    )


def registrar_pago(*, reserva, monto, metodo_pago, referencia="", tipo=PagoReserva.TIPO_TOTAL, actor=None):
    try:
        monto = parse_money(monto, default=None)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError("El monto del pago no es valido.") from exc

    if monto <= 0:
        raise ValidationError("El monto del pago debe ser mayor a cero.")
    if reserva.estado in {Reserva.ESTADO_CANCELADA, Reserva.ESTADO_NO_ASISTIO}:
        raise ValidationError("No se pueden registrar pagos para una cita cerrada.")
    if tipo not in {choice[0] for choice in PagoReserva.TIPOS}:
        raise ValidationError("El tipo de pago no es valido.")
    if metodo_pago not in {choice[0] for choice in PagoReserva.METODOS}:
        raise ValidationError("El metodo de pago no es valido.")

    return PagoReserva.objects.create(
        reserva=reserva,
        monto=monto,
        metodo_pago=metodo_pago,
        referencia=referencia.strip(),
        tipo=tipo,
        registrado_por=actor,
    )


def crear_reserva(
    *,
    cliente=None,
    cliente_invitado=None,
    servicio,
    fecha_inicio,
    notas="",
    origen=Reserva.ORIGEN_AUTENTICADO,
    actor=None,
    pago_data=None,
):
    if bool(cliente) == bool(cliente_invitado):
        raise ValidationError("La reserva debe quedar asociada a un cliente registrado o a un invitado.")

    fecha_fin = calcular_fecha_fin(servicio, fecha_inicio)
    validar_reserva(servicio=servicio, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)

    hay_pago = bool(pago_data)
    if origen == Reserva.ORIGEN_INVITADO and not hay_pago:
        raise ValidationError("Las reservas sin autenticacion deben registrar el pago en el mismo paso.")

    estado_inicial = Reserva.ESTADO_CONFIRMADA if hay_pago or origen == Reserva.ORIGEN_INVITADO else Reserva.ESTADO_PROGRAMADA
    reserva = Reserva.objects.create(
        cliente=cliente,
        cliente_invitado=cliente_invitado,
        servicio=servicio,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        estado=estado_inicial,
        origen_reserva=origen,
        notas=notas.strip(),
        creada_por=actor,
    )
    registrar_historial_estado(
        reserva=reserva,
        estado_anterior="",
        estado_nuevo=estado_inicial,
        usuario_actor=actor or cliente,
        observacion="Reserva creada.",
    )

    pago = None
    if pago_data:
        pago = registrar_pago(
            reserva=reserva,
            monto=pago_data["monto"],
            metodo_pago=pago_data["metodo_pago"],
            referencia=pago_data.get("referencia", ""),
            tipo=pago_data.get("tipo", PagoReserva.TIPO_TOTAL),
            actor=actor or cliente,
        )
    return reserva, pago


def actualizar_reserva(*, reserva, servicio, fecha_inicio, notas="", actor=None):
    if reserva.estado in {Reserva.ESTADO_FINALIZADA, Reserva.ESTADO_CANCELADA, Reserva.ESTADO_NO_ASISTIO}:
        raise ValidationError("No se puede editar una cita cerrada.")

    fecha_fin = calcular_fecha_fin(servicio, fecha_inicio)
    validar_reserva(
        servicio=servicio,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        exclude_reserva_id=reserva.id,
    )

    reserva.servicio = servicio
    reserva.fecha_inicio = fecha_inicio
    reserva.fecha_fin = fecha_fin
    reserva.notas = notas.strip()
    reserva.save()
    registrar_historial_estado(
        reserva=reserva,
        estado_anterior=reserva.estado,
        estado_nuevo=reserva.estado,
        usuario_actor=actor,
        observacion="Reserva actualizada.",
    )
    return reserva


def cambiar_estado_reserva(*, reserva, nuevo_estado, actor=None, observacion=""):
    estado_actual = reserva.estado
    if estado_actual == nuevo_estado:
        return reserva

    if estado_actual not in TRANSICIONES_VALIDAS or nuevo_estado not in TRANSICIONES_VALIDAS[estado_actual]:
        raise ValidationError(f"No se puede pasar de {estado_actual} a {nuevo_estado}.")

    if nuevo_estado == Reserva.ESTADO_EN_PROCESO:
        reserva.fecha_inicio_real = timezone.now()
    if nuevo_estado == Reserva.ESTADO_FINALIZADA:
        if estado_actual != Reserva.ESTADO_EN_PROCESO:
            raise ValidationError("La cita debe estar en proceso antes de finalizar.")
        reserva.fecha_fin_real = timezone.now()
    if nuevo_estado == Reserva.ESTADO_CANCELADA:
        reserva.motivo_cancelacion = observacion.strip()

    reserva.estado = nuevo_estado
    reserva.save()
    registrar_historial_estado(
        reserva=reserva,
        estado_anterior=estado_actual,
        estado_nuevo=nuevo_estado,
        usuario_actor=actor,
        observacion=observacion,
    )
    return reserva


def construir_token_comprobante(pago):
    return signing.dumps({"pago_id": pago.id}, salt="citas-comprobante")


def resolver_token_comprobante(token, max_age=60 * 60 * 24):
    payload = signing.loads(token, salt="citas-comprobante", max_age=max_age)
    return PagoReserva.objects.select_related(
        "reserva",
        "reserva__cliente",
        "reserva__cliente_invitado",
        "reserva__servicio",
    ).get(
        id=payload["pago_id"]
    )


def reservas_visibles_para_usuario(usuario):
    reservas = Reserva.objects.select_related(
        "cliente", "cliente_invitado", "servicio", "servicio__profesional", "creada_por"
    ).prefetch_related("pagos", "historial_estados")
    if usuario.rol != Usuario.ROL_ADMIN:
        reservas = reservas.filter(cliente=usuario)
    return reservas


def pagos_reserva_por_validos(reserva):
    return reserva.pagos.filter(estado=PagoReserva.ESTADO_CONFIRMADO).order_by("-fecha_pago", "-id")


def puede_editar_reserva(reserva):
    return reserva.estado not in {
        Reserva.ESTADO_FINALIZADA,
        Reserva.ESTADO_CANCELADA,
        Reserva.ESTADO_NO_ASISTIO,
    }


def reservas_para_calendario(usuario):
    qs = Reserva.objects.select_related(
        "cliente", "cliente_invitado", "servicio", "servicio__profesional"
    ).prefetch_related("pagos")
    if usuario.rol != Usuario.ROL_ADMIN:
        qs = qs.filter(cliente=usuario)
    return qs


def resumen_dashboard_admin():
    hoy = timezone.localdate()
    inicio_semana = hoy - timedelta(days=hoy.weekday())
    inicio_mes = hoy.replace(day=1)
    fin_semana = inicio_semana + timedelta(days=7)
    if hoy.month == 12:
        inicio_mes_siguiente = hoy.replace(year=hoy.year + 1, month=1, day=1)
    else:
        inicio_mes_siguiente = hoy.replace(month=hoy.month + 1, day=1)
    reservas = Reserva.objects.all()
    return {
        "reservas_hoy": reservas.filter(fecha_inicio__date=hoy).count(),
        "reservas_semana": reservas.filter(
            fecha_inicio__date__gte=inicio_semana,
            fecha_inicio__date__lt=fin_semana,
        ).count(),
        "reservas_mes": reservas.filter(
            fecha_inicio__date__gte=inicio_mes,
            fecha_inicio__date__lt=inicio_mes_siguiente,
        ).count(),
        "pendientes": reservas.filter(
            estado__in=[Reserva.ESTADO_PROGRAMADA, Reserva.ESTADO_CONFIRMADA]
        ).count(),
    }

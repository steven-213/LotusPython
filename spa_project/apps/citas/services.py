from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import ProgrammingError, transaction
from django.db.models import Sum, Count, Avg, Q, OuterRef, Subquery, Case, When, DecimalField, Value, DateField
from django.db.models.functions import TruncDate, Coalesce
from django.utils import timezone

from apps.common.currency import parse_money, format_money
from apps.citas.models import PagoReserva, Reserva, ReservaHistorialEstado, Servicio
from apps.sesiones.models import Usuario


ESTADOS_CONFLICTIVOS = {
    Reserva.ESTADO_PROGRAMADA,
    Reserva.ESTADO_CONFIRMADA,
    Reserva.ESTADO_EN_PROCESO,
}

INTERVALO_RESERVA_MINUTOS = 15
DIAS_GRACIA_CANCELACION_AUTOMATICA = 5
DIAS_ANTIGUEDAD_HISTORIAL = 7

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


def _filtrar_por_archivado(queryset, archivada=False):
    try:
        if archivada:
            return queryset.filter(archivada_en__isnull=False)
        return queryset.filter(archivada_en__isnull=True)
    except ProgrammingError:
        return queryset if not archivada else queryset.none()


def _formatear_hora_input(hora):
    return hora.strftime("%H:%M")


def configuracion_horario_reserva():
    dias = {indice: None for indice in range(7)}
    for weekday_python, (apertura, cierre) in HORARIOS_ATENCION.items():
        weekday_js = (weekday_python + 1) % 7
        dias[weekday_js] = {
            "apertura": _formatear_hora_input(apertura),
            "cierre": _formatear_hora_input(cierre),
        }
    return {
        "dias": dias,
        "intervalo_minutos": INTERVALO_RESERVA_MINUTOS,
    }


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
    if (
        fecha_inicio_local.minute != 0
        or fecha_inicio_local.second != 0
        or fecha_inicio_local.microsecond != 0
    ):
        raise ValidationError(
            f"Las citas solo se pueden reservar en horas exactas. Horario permitido: {horario_legible}."
        )
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


def _redondear_hacia_arriba_intervalo(fecha):
    fecha = fecha.replace(second=0, microsecond=0)
    residuo = fecha.minute % INTERVALO_RESERVA_MINUTOS
    if residuo == 0:
        return fecha
    return fecha + timedelta(minutes=INTERVALO_RESERVA_MINUTOS - residuo)


def _combinar_fecha_hora_local(fecha_reserva, hora_reserva):
    return timezone.make_aware(
        datetime.combine(fecha_reserva, hora_reserva),
        timezone.get_current_timezone(),
    )


def _filtro_profesional_reserva(profesional):
    return Q(profesional=profesional) | Q(profesional__isnull=True, servicio__profesional=profesional)


def _reservas_conflictivas_profesional(*, profesional, fecha_inicio, fecha_fin, exclude_reserva_id=None):
    conflictos = Reserva.objects.select_related(
        "cliente", "servicio", "servicio__profesional", "profesional"
    ).filter(
        _filtro_profesional_reserva(profesional),
        estado__in=ESTADOS_CONFLICTIVOS,
        fecha_inicio__lt=fecha_fin,
        fecha_fin__gt=fecha_inicio,
    )
    if exclude_reserva_id:
        conflictos = conflictos.exclude(id=exclude_reserva_id)
    return conflictos


def obtener_conflicto_reserva(*, servicio, fecha_inicio, fecha_fin, profesional=None, exclude_reserva_id=None):
    profesional = profesional or servicio.profesional
    if not profesional:
        return None

    return _reservas_conflictivas_profesional(
        profesional=profesional,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        exclude_reserva_id=exclude_reserva_id,
    ).first()


def obtener_horas_disponibles_reserva(*, servicio, fecha_reserva, exclude_reserva_id=None):
    if not servicio.activo:
        raise ValidationError("El servicio seleccionado no esta disponible.")
    if not servicio.profesional_id:
        raise ValidationError("El servicio no tiene una profesional asignada.")
    if fecha_reserva < timezone.localdate():
        raise ValidationError("No hay horarios disponibles para fechas anteriores a hoy.")

    inicio_dia = _combinar_fecha_hora_local(fecha_reserva, time.min)
    horario = obtener_horario_atencion(inicio_dia)
    if not horario:
        return []

    apertura, cierre = horario
    duracion_minutos = servicio.duracion_minutos or 60
    duracion = timedelta(minutes=duracion_minutos)
    apertura_dt = _combinar_fecha_hora_local(fecha_reserva, apertura)
    cierre_dt = _combinar_fecha_hora_local(fecha_reserva, cierre)
    ultimo_inicio_dt = cierre_dt - duracion
    if ultimo_inicio_dt < apertura_dt:
        return []

    ahora_local = timezone.localtime(timezone.now())
    primer_inicio_dt = apertura_dt
    if fecha_reserva == ahora_local.date():
        primer_inicio_dt = max(primer_inicio_dt, _redondear_hacia_arriba_intervalo(ahora_local))
    if primer_inicio_dt > ultimo_inicio_dt:
        return []

    reservas_ocupadas = list(
        _reservas_conflictivas_profesional(
            profesional=servicio.profesional,
            fecha_inicio=apertura_dt,
            fecha_fin=cierre_dt,
            exclude_reserva_id=exclude_reserva_id,
        ).values_list("fecha_inicio", "fecha_fin")
    )

    horas_disponibles = []
    cursor = primer_inicio_dt
    while cursor <= ultimo_inicio_dt:
        fecha_fin = cursor + duracion
        tiene_cruce = any(
            reserva_inicio < fecha_fin and reserva_fin > cursor
            for reserva_inicio, reserva_fin in reservas_ocupadas
        )
        if not tiene_cruce:
            horas_disponibles.append(timezone.localtime(cursor).strftime("%H:%M"))
        cursor += timedelta(minutes=INTERVALO_RESERVA_MINUTOS)

    return horas_disponibles


def validar_reserva(*, servicio, fecha_inicio, fecha_fin, profesional=None, exclude_reserva_id=None):
    ahora = timezone.now()
    profesional = profesional or servicio.profesional
    if not servicio.activo:
        raise ValidationError("El servicio seleccionado no esta disponible.")
    if not profesional:
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
        profesional=profesional,
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


def _validar_monto_pago_reserva(*, reserva, monto, tipo):
    saldo_pendiente = reserva.saldo_pendiente
    if saldo_pendiente <= 0:
        raise ValidationError("La cita ya no tiene saldo pendiente por cobrar.")

    if tipo == PagoReserva.TIPO_TOTAL:
        if monto <= 0:
            return
        if monto != saldo_pendiente:
            raise ValidationError(
                f"Para registrar un pago completo debes cobrar exactamente el saldo pendiente ({format_money(saldo_pendiente)})."
            )
        return

    if monto > saldo_pendiente:
        raise ValidationError(
            f"El monto supera el saldo pendiente de la cita ({format_money(saldo_pendiente)})."
        )

    if tipo == PagoReserva.TIPO_ANTICIPO and monto >= saldo_pendiente:
        raise ValidationError(
            f"El anticipo debe ser menor al saldo pendiente ({format_money(saldo_pendiente)}). Si vas a cobrar todo, usa la opcion de pago completo."
        )


def registrar_pago(*, reserva, monto, metodo_pago, referencia="", tipo=PagoReserva.TIPO_TOTAL, actor=None):
    try:
        monto = parse_money(monto, default=None)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError("El monto del pago no es valido.") from exc

    if tipo == PagoReserva.TIPO_TOTAL and (monto is None or monto <= 0):
        monto = reserva.saldo_pendiente
    elif monto <= 0:
        raise ValidationError("El monto del pago debe ser mayor a cero.")
    if reserva.estado in {Reserva.ESTADO_CANCELADA, Reserva.ESTADO_NO_ASISTIO}:
        raise ValidationError("No se pueden registrar pagos para una cita cerrada.")
    if tipo not in {choice[0] for choice in PagoReserva.TIPOS}:
        raise ValidationError("El tipo de pago no es valido.")
    if metodo_pago not in {choice[0] for choice in PagoReserva.METODOS}:
        raise ValidationError("El metodo de pago no es valido.")
    _validar_monto_pago_reserva(reserva=reserva, monto=monto, tipo=tipo)

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
    cliente,
    servicio,
    fecha_inicio,
    notas="",
    origen=Reserva.ORIGEN_AUTENTICADO,
    actor=None,
    pago_data=None,
):
    if not cliente:
        raise ValidationError("La reserva debe quedar asociada a un cliente registrado.")

    fecha_fin = calcular_fecha_fin(servicio, fecha_inicio)
    profesional = servicio.profesional
    validar_reserva(servicio=servicio, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin, profesional=profesional)

    hay_pago = bool(pago_data)
    estado_inicial = Reserva.ESTADO_CONFIRMADA if hay_pago else Reserva.ESTADO_PROGRAMADA
    reserva = Reserva.objects.create(
        cliente=cliente,
        servicio=servicio,
        profesional=profesional,
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
    profesional = reserva.profesional if reserva.servicio_id == servicio.id and reserva.profesional_id else servicio.profesional
    validar_reserva(
        servicio=servicio,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        profesional=profesional,
        exclude_reserva_id=reserva.id,
    )

    reserva.servicio = servicio
    reserva.profesional = profesional
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


def actualizar_profesional_reserva(*, reserva, profesional, actor=None):
    if reserva.estado in {Reserva.ESTADO_FINALIZADA, Reserva.ESTADO_CANCELADA, Reserva.ESTADO_NO_ASISTIO}:
        raise ValidationError("No se puede reasignar la profesional de una cita cerrada.")
    if not profesional:
        raise ValidationError("Debes seleccionar o crear una profesional valida.")
    if reserva.profesional_id == profesional.id:
        return reserva

    validar_reserva(
        servicio=reserva.servicio,
        fecha_inicio=reserva.fecha_inicio,
        fecha_fin=reserva.fecha_fin,
        profesional=profesional,
        exclude_reserva_id=reserva.id,
    )

    reserva.profesional = profesional
    reserva.save(update_fields=["profesional", "updated_at"])
    registrar_historial_estado(
        reserva=reserva,
        estado_anterior=reserva.estado,
        estado_nuevo=reserva.estado,
        usuario_actor=actor,
        observacion=f"Profesional reasignada a {profesional.nombre}.",
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
        if not reserva.esta_pagada:
            raise ValidationError("No puedes finalizar una cita con saldo pendiente. Registra el pago restante primero.")
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


def cancelar_reservas_vencidas(*, actor=None):
    ahora = timezone.now()
    fecha_limite = ahora - timedelta(days=DIAS_GRACIA_CANCELACION_AUTOMATICA)
    estados_vencibles = [
        Reserva.ESTADO_PROGRAMADA,
        Reserva.ESTADO_CONFIRMADA,
        Reserva.ESTADO_EN_PROCESO,
    ]
    observacion = "Cancelada automaticamente por superar el plazo sin finalizar."
    try:
        reservas_vencidas = list(
            Reserva.objects.filter(
                estado__in=estados_vencibles,
                fecha_inicio__lt=fecha_limite,
                archivada_en__isnull=True,
            ).values("id", "estado")
        )
    except ProgrammingError:
        return 0
    if not reservas_vencidas:
        return 0

    reserva_ids = [reserva["id"] for reserva in reservas_vencidas]
    with transaction.atomic():
        Reserva.objects.filter(id__in=reserva_ids).update(
            estado=Reserva.ESTADO_CANCELADA,
            motivo_cancelacion=observacion,
            updated_at=ahora,
        )
        ReservaHistorialEstado.objects.bulk_create(
            [
                ReservaHistorialEstado(
                    reserva_id=reserva["id"],
                    estado_anterior=reserva["estado"],
                    estado_nuevo=Reserva.ESTADO_CANCELADA,
                    usuario_actor=actor,
                    observacion=observacion,
                )
                for reserva in reservas_vencidas
            ]
        )
    return len(reservas_vencidas)


def archivar_reservas_antiguas(*, actor=None):
    ahora = timezone.now()
    fecha_limite = ahora - timedelta(days=DIAS_ANTIGUEDAD_HISTORIAL)
    estados_historial = [
        Reserva.ESTADO_FINALIZADA,
        Reserva.ESTADO_CANCELADA,
        Reserva.ESTADO_NO_ASISTIO,
    ]
    observacion = "Movida automaticamente al historial."
    try:
        reservas_antiguas = list(
            Reserva.objects.filter(
                estado__in=estados_historial,
                fecha_inicio__lt=fecha_limite,
                archivada_en__isnull=True,
            ).values("id", "estado")
        )
    except ProgrammingError:
        return 0
    if not reservas_antiguas:
        return 0

    reserva_ids = [reserva["id"] for reserva in reservas_antiguas]
    with transaction.atomic():
        Reserva.objects.filter(id__in=reserva_ids).update(
            archivada_en=ahora,
            archivada_automaticamente=True,
            updated_at=ahora,
        )
        ReservaHistorialEstado.objects.bulk_create(
            [
                ReservaHistorialEstado(
                    reserva_id=reserva["id"],
                    estado_anterior=reserva["estado"],
                    estado_nuevo=reserva["estado"],
                    usuario_actor=actor,
                    observacion=observacion,
                )
                for reserva in reservas_antiguas
            ]
        )
    return len(reservas_antiguas)


def mantenimiento_reservas_dashboard(*, actor=None):
    canceladas = cancelar_reservas_vencidas(actor=actor)
    archivadas = archivar_reservas_antiguas(actor=actor)
    return {"canceladas": canceladas, "archivadas": archivadas}


def construir_token_comprobante(pago):
    return signing.dumps({"pago_id": pago.id}, salt="citas-comprobante")


def resolver_token_comprobante(token, max_age=60 * 60 * 24):
    payload = signing.loads(token, salt="citas-comprobante", max_age=max_age)
    return PagoReserva.objects.select_related(
        "reserva",
        "reserva__cliente",
        "reserva__servicio",
        "reserva__profesional",
    ).get(
        id=payload["pago_id"]
    )


def reservas_visibles_para_usuario(usuario):
    reservas = Reserva.objects.select_related(
        "cliente", "servicio", "servicio__profesional", "profesional", "creada_por"
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
        "cliente", "servicio", "servicio__profesional", "profesional"
    ).prefetch_related("pagos")
    if usuario.rol != Usuario.ROL_ADMIN:
        qs = qs.filter(cliente=usuario)
    return qs



def _reservas_facturadas_queryset():
    return Reserva.objects.filter(
        estado=Reserva.ESTADO_FINALIZADA,
    ).annotate(
        fecha_facturacion=Case(
            When(fecha_fin_real__isnull=False, then=TruncDate("fecha_fin_real")),
            default=TruncDate("fecha_inicio"),
            output_field=DateField(),
        ),
    )


def _agregar_ingresos_facturados(queryset):
    return queryset.aggregate(
        servicios_total=Coalesce(
            Sum("servicio__precio"),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        ),
        productos_total=Coalesce(
            Sum("venta_asociada__total"),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        ),
        cantidad=Count("id"),
    )


def _serializar_ingresos_facturados(aggregate_result):
    servicios_total = aggregate_result["servicios_total"] or Decimal("0.00")
    productos_total = aggregate_result["productos_total"] or Decimal("0.00")
    total_facturado = servicios_total + productos_total
    return {
        "servicios_monto": format_money(servicios_total),
        "productos_monto": format_money(productos_total),
        "total_monto": format_money(total_facturado),
        "cantidad": aggregate_result["cantidad"] or 0,
    }


def _calcular_ingresos_citas_facturadas():
    """Calcula ingresos de citas finalizadas tomando como referencia su fecha real de cierre."""
    hoy = timezone.localdate()
    inicio_semana = hoy - timedelta(days=hoy.weekday())
    reservas_facturadas = _reservas_facturadas_queryset()

    ingresos_todas = _agregar_ingresos_facturados(reservas_facturadas)
    ingresos_hoy = _agregar_ingresos_facturados(
        reservas_facturadas.filter(fecha_facturacion=hoy)
    )
    ingresos_semana = _agregar_ingresos_facturados(
        reservas_facturadas.filter(
            fecha_facturacion__gte=inicio_semana,
            fecha_facturacion__lt=inicio_semana + timedelta(days=7),
        )
    )

    inicio_mes = hoy.replace(day=1)
    if hoy.month == 12:
        inicio_mes_siguiente = hoy.replace(year=hoy.year + 1, month=1, day=1)
    else:
        inicio_mes_siguiente = hoy.replace(month=hoy.month + 1, day=1)

    ingresos_mes = _agregar_ingresos_facturados(
        reservas_facturadas.filter(
            fecha_facturacion__gte=inicio_mes,
            fecha_facturacion__lt=inicio_mes_siguiente,
        )
    )

    return {
        "todas": _serializar_ingresos_facturados(ingresos_todas),
        "hoy": _serializar_ingresos_facturados(ingresos_hoy),
        "semana": _serializar_ingresos_facturados(ingresos_semana),
        "mes": _serializar_ingresos_facturados(ingresos_mes),
    }


def resumen_dashboard_admin():
    hoy = timezone.localdate()
    inicio_semana = hoy - timedelta(days=hoy.weekday())
    inicio_mes = hoy.replace(day=1)
    fin_semana = inicio_semana + timedelta(days=7)
    if hoy.month == 12:
        inicio_mes_siguiente = hoy.replace(year=hoy.year + 1, month=1, day=1)
    else:
        inicio_mes_siguiente = hoy.replace(month=hoy.month + 1, day=1)
    
    try:
        reservas_activas = Reserva.objects.filter(archivada_en__isnull=True)
        ingresos_historial = _agregar_ingresos_facturados(
            _reservas_facturadas_queryset().filter(archivada_en__isnull=False)
        )
        reservas_historial = Reserva.objects.filter(archivada_en__isnull=False).count()
    except ProgrammingError:
        reservas_activas = Reserva.objects.all()
        ingresos_historial = _agregar_ingresos_facturados(_reservas_facturadas_queryset().none())
        reservas_historial = 0
    ingresos_por_periodo = _calcular_ingresos_citas_facturadas()
    
    return {
        "reservas_hoy": reservas_activas.filter(fecha_inicio__date=hoy).count(),
        "reservas_semana": reservas_activas.filter(
            fecha_inicio__date__gte=inicio_semana,
            fecha_inicio__date__lt=fin_semana,
        ).count(),
        "reservas_mes": reservas_activas.filter(
            fecha_inicio__date__gte=inicio_mes,
            fecha_inicio__date__lt=inicio_mes_siguiente,
        ).count(),
        "reservas_todas": reservas_activas.count(),
        "reservas_historial": reservas_historial,
        "pendientes": reservas_activas.filter(
            estado__in=[Reserva.ESTADO_PROGRAMADA, Reserva.ESTADO_CONFIRMADA]
        ).count(),
        "ingresos_por_periodo": {
            **ingresos_por_periodo,
            "historial": ingresos_historial,
        },
    }

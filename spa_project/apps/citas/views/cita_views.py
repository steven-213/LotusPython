from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO
from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Case, DecimalField, IntegerField, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import Coalesce
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from apps.common.currency import format_money, parse_money
from apps.citas.models import PagoReserva, Profesional, Reserva, Servicio
from apps.citas.services import (
    actualizar_reserva,
    actualizar_profesional_reserva,
    cambiar_estado_reserva,
    cancelar_reservas_vencidas,
    configuracion_horario_reserva,
    crear_reserva,
    mantenimiento_reservas_dashboard,
    pagos_reserva_por_validos,
    puede_editar_reserva,
    reservas_visibles_para_usuario,
    resumen_horario_atencion,
    resumen_dashboard_admin,
    _filtrar_por_archivado,
)
from apps.inventario.services import anotar_stock_disponible
from apps.sesiones.decorators import admin_required_session, login_required_session
from apps.sesiones.models import Usuario
from apps.ventas.services import registrar_venta_desde_reserva


def _usuario_actual(request):
    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        return None
    return Usuario.objects.filter(id=usuario_id).first()


def _usuario_admin(request):
    usuario = _usuario_actual(request)
    return usuario if usuario and usuario.rol == Usuario.ROL_ADMIN else None


def _parse_datetime_local(value: str):
    if not value:
        raise ValidationError("Debes seleccionar una fecha y hora.")
    try:
        fecha = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError("La fecha y hora seleccionadas no son validas.") from exc
    if timezone.is_naive(fecha):
        fecha = timezone.make_aware(fecha, timezone.get_current_timezone())
    return fecha


def _extraer_fecha_inicio_reserva(request):
    fecha_inicio = (request.POST.get("fecha_inicio") or "").strip()
    if fecha_inicio:
        return _parse_datetime_local(fecha_inicio)

    fecha_reserva = (request.POST.get("fecha_reserva") or "").strip()
    hora_reserva = (request.POST.get("hora_reserva") or "").strip()
    if not fecha_reserva or not hora_reserva:
        raise ValidationError("Debes seleccionar una fecha y hora.")
    return _parse_datetime_local(f"{fecha_reserva}T{hora_reserva}")


def _descomponer_fecha_formulario(valor):
    if not valor:
        return {
            "fecha_inicio_value": "",
            "fecha_reserva_value": "",
            "hora_reserva_value": "",
        }

    if isinstance(valor, str):
        raw = valor.strip()
        if not raw:
            return {
                "fecha_inicio_value": "",
                "fecha_reserva_value": "",
                "hora_reserva_value": "",
            }
        try:
            fecha = datetime.fromisoformat(raw)
        except ValueError:
            return {
                "fecha_inicio_value": raw,
                "fecha_reserva_value": raw[:10] if len(raw) >= 10 else "",
                "hora_reserva_value": raw[11:16] if len(raw) >= 16 else "",
            }
    else:
        fecha = timezone.localtime(valor) if timezone.is_aware(valor) else valor

    return {
        "fecha_inicio_value": fecha.strftime("%Y-%m-%dT%H:%M"),
        "fecha_reserva_value": fecha.strftime("%Y-%m-%d"),
        "hora_reserva_value": fecha.strftime("%H:%M"),
    }


def _contexto_fecha_formulario(request, reserva=None):
    fecha_inicio = (request.POST.get("fecha_inicio") or "").strip()
    fecha_reserva = (request.POST.get("fecha_reserva") or "").strip()
    hora_reserva = (request.POST.get("hora_reserva") or "").strip()

    if fecha_inicio:
        valores = _descomponer_fecha_formulario(fecha_inicio)
        fecha_reserva = fecha_reserva or valores["fecha_reserva_value"]
        hora_reserva = hora_reserva or valores["hora_reserva_value"]
        return {
            "fecha_inicio_value": valores["fecha_inicio_value"],
            "fecha_reserva_value": fecha_reserva,
            "hora_reserva_value": hora_reserva,
        }

    if fecha_reserva or hora_reserva:
        return {
            "fecha_inicio_value": f"{fecha_reserva}T{hora_reserva}" if fecha_reserva and hora_reserva else "",
            "fecha_reserva_value": fecha_reserva,
            "hora_reserva_value": hora_reserva,
        }

    return _descomponer_fecha_formulario(reserva.fecha_inicio) if reserva else {
        "fecha_inicio_value": "",
        "fecha_reserva_value": "",
        "hora_reserva_value": "",
    }


def _contexto_formulario_reserva(*, request, usuario, servicios, reserva=None, servicio_preseleccionado=""):
    return {
        "usuario": usuario,
        "servicios": servicios,
        "reserva": reserva,
        "servicio_preseleccionado": servicio_preseleccionado,
        "metodos_pago": PagoReserva.METODOS,
        "horario_atencion": resumen_horario_atencion(),
        "configuracion_horario_reserva": configuracion_horario_reserva(),
        **_contexto_fecha_formulario(request, reserva),
    }


def _productos_facturables():
    from apps.inventario.models import Inventario, Producto

    precio_reciente = (
        Inventario.objects.filter(
            producto=OuterRef("pk"),
            stock__gt=0,
        )
        .order_by("-fecha_ingreso", "-id")
        .values("precio_venta")[:1]
    )

    return (
        anotar_stock_disponible(Producto.objects.filter(activo=True))
        .annotate(
            precio_facturable=Coalesce(
                Subquery(precio_reciente, output_field=DecimalField(max_digits=10, decimal_places=2)),
                "precio_venta",
                Value(0),
                output_field=DecimalField(max_digits=10, decimal_places=2),
            )
        )
        .filter(stock_disponible__gt=0, precio_facturable__gt=0)
        .order_by("nombre")
    )


def _extraer_pago_publico(request, servicio, requerido=False, monto=None):
    quiere_pagar = requerido or request.POST.get("pagar_ahora") == "1"
    if not quiere_pagar:
        return None

    metodo_pago = (request.POST.get("metodo_pago") or "").strip()
    referencia = (request.POST.get("referencia_pago") or "").strip()
    if not metodo_pago:
        raise ValidationError("Debes seleccionar un metodo de pago.")

    return {
        "monto": monto if monto is not None else servicio.precio,
        "metodo_pago": metodo_pago,
        "referencia": referencia,
        "tipo": PagoReserva.TIPO_TOTAL,
    }


def _extraer_pago_admin(request, reserva):
    metodo_pago = (request.POST.get("metodo_pago") or "").strip()
    if not metodo_pago:
        raise ValidationError("Debes seleccionar un metodo de pago.")

    monto_raw = (request.POST.get("monto") or "").strip() or str(reserva.saldo_pendiente)
    try:
        monto = parse_money(monto_raw, default=None)
    except InvalidOperation as exc:
        raise ValidationError("El monto del pago no es valido.") from exc

    return {
        "monto": monto,
        "metodo_pago": metodo_pago,
        "referencia": (request.POST.get("referencia_pago") or "").strip(),
        "tipo": (request.POST.get("tipo_pago") or PagoReserva.TIPO_TOTAL).strip() or PagoReserva.TIPO_TOTAL,
    }


def _extraer_productos_admin(request):
    producto_ids = request.POST.getlist("producto_id[]") or request.POST.getlist("producto_id")
    cantidades = request.POST.getlist("cantidad_producto[]") or request.POST.getlist("cantidad_producto")
    if not producto_ids and not cantidades:
        return []
    if len(producto_ids) != len(cantidades):
        raise ValidationError("No fue posible leer correctamente los productos seleccionados.")

    producto_ids_limpios = [valor.strip() for valor in producto_ids if (valor or "").strip()]
    if not producto_ids_limpios:
        return []

    productos_disponibles = {
        producto.id: producto
        for producto in _productos_facturables().filter(id__in=producto_ids_limpios)
    }
    items_por_producto = {}
    for producto_id_raw, cantidad_raw in zip(producto_ids, cantidades):
        producto_id_raw = (producto_id_raw or "").strip()
        if not producto_id_raw:
            continue
        try:
            producto_id = int(producto_id_raw)
            cantidad = int((cantidad_raw or "").strip())
        except (TypeError, ValueError) as exc:
            raise ValidationError("Cada producto del carrito debe tener una cantidad valida.") from exc

        producto = productos_disponibles.get(producto_id)
        if not producto:
            raise ValidationError("Uno de los productos seleccionados no esta disponible para facturar.")
        if cantidad <= 0:
            raise ValidationError(f"La cantidad para {producto.nombre} debe ser mayor a cero.")
        if hasattr(producto, "precio_facturable"):
            producto.precio_venta = producto.precio_facturable

        item = items_por_producto.setdefault(
            producto.id,
            {
                "producto": producto,
                "cantidad": 0,
            },
        )
        item["cantidad"] += cantidad

    return list(items_por_producto.values())


def _extraer_profesional_desde_request(request):
    profesional_id = (request.POST.get("profesional_id") or "").strip()
    profesional_nombre = (request.POST.get("profesional_nombre") or "").strip()

    if profesional_nombre:
        profesional = Profesional.objects.filter(nombre__iexact=profesional_nombre).first()
        if profesional:
            if not profesional.activo:
                profesional.activo = True
                profesional.save(update_fields=["activo", "updated_at"])
            return profesional
        return Profesional.objects.create(nombre=profesional_nombre)
    if profesional_id:
        return get_object_or_404(Profesional, id=profesional_id, activo=True)
    raise ValidationError("Debes seleccionar una profesional o escribir una nueva.")


def _asegurar_propiedad_reserva(request, reserva):
    usuario = _usuario_actual(request)
    if not usuario:
        raise Http404()
    if usuario.rol == Usuario.ROL_ADMIN or reserva.cliente_id == usuario.id:
        return usuario
    raise Http404()


def _estado_puede_pasar_a(reserva, nuevo_estado):
    from apps.citas.services import TRANSICIONES_VALIDAS

    return nuevo_estado in TRANSICIONES_VALIDAS.get(reserva.estado, set())


def _reservas_admin_queryset():
    return Reserva.objects.select_related(
        "cliente",
        "profesional",
        "servicio",
        "servicio__profesional",
        "venta_asociada",
    ).prefetch_related("pagos", "historial_estados", "venta_asociada__detalles__producto")


def _leer_filtros_dashboard(request):
    atajo = (request.GET.get("atajo") or "").strip().lower()
    if atajo not in {"hoy", "semana", "mes", "todas", "pendientes", "historial"}:
        atajo = ""
    return {
        "atajo": atajo,
        "estado": (request.GET.get("estado") or "").strip(),
        "profesional_id": (request.GET.get("profesional_id") or "").strip(),
        "asistencia": (request.GET.get("asistencia") or "").strip(),
        "q": (request.GET.get("q") or "").strip(),
    }


def _querystring_dashboard(filtros, **extras):
    params = {
        "atajo": filtros.get("atajo", ""),
        "estado": filtros.get("estado", ""),
        "profesional_id": filtros.get("profesional_id", ""),
        "asistencia": filtros.get("asistencia", ""),
        "q": filtros.get("q", ""),
    }
    params.update(extras)
    limpio = {key: value for key, value in params.items() if value not in {"", None}}
    if not limpio:
        return ""
    return urlencode(limpio)


def _aplicar_atajo_dashboard(queryset, atajo):
    hoy = timezone.localdate()
    inicio_semana = hoy - timedelta(days=hoy.weekday())
    if hoy.month == 12:
        inicio_mes_siguiente = hoy.replace(year=hoy.year + 1, month=1, day=1)
    else:
        inicio_mes_siguiente = hoy.replace(month=hoy.month + 1, day=1)

    if atajo == "historial":
        queryset = _filtrar_por_archivado(queryset, archivada=True)
    else:
        queryset = _filtrar_por_archivado(queryset, archivada=False)
    if atajo == "hoy":
        return queryset.filter(fecha_inicio__date=hoy)
    if atajo == "semana":
        return queryset.filter(
            fecha_inicio__date__gte=inicio_semana,
            fecha_inicio__date__lt=inicio_semana + timedelta(days=7),
        )
    if atajo == "mes":
        return queryset.filter(
            fecha_inicio__date__gte=hoy.replace(day=1),
            fecha_inicio__date__lt=inicio_mes_siguiente,
        )
    if atajo == "todas":
        return queryset
    if atajo == "pendientes":
        return queryset.filter(
            estado__in=[Reserva.ESTADO_PROGRAMADA, Reserva.ESTADO_CONFIRMADA]
        )
    return queryset


def _aplicar_filtros_dashboard(queryset, filtros):
    queryset = _aplicar_atajo_dashboard(queryset, filtros["atajo"])

    if filtros["estado"]:
        queryset = queryset.filter(estado=filtros["estado"])
    if filtros["profesional_id"]:
        queryset = queryset.filter(
            Q(profesional_id=filtros["profesional_id"])
            | Q(profesional__isnull=True, servicio__profesional_id=filtros["profesional_id"])
        )
    if filtros["asistencia"] == "asistio":
        queryset = queryset.filter(
            estado__in=[Reserva.ESTADO_EN_PROCESO, Reserva.ESTADO_FINALIZADA]
        )
    elif filtros["asistencia"] == "no_asistio":
        queryset = queryset.filter(estado=Reserva.ESTADO_NO_ASISTIO)
    if filtros["q"]:
        q = filtros["q"]
        consulta = (
            Q(cliente__nombre__icontains=q)
            | Q(cliente__apellido__icontains=q)
            | Q(servicio__nombre__icontains=q)
        )
        if q.isdigit():
            consulta |= Q(cliente__documento=int(q))
        queryset = queryset.filter(consulta)
    return queryset


def _ordenar_reservas_dashboard(queryset):
    return queryset.order_by(
        Case(
            When(estado=Reserva.ESTADO_EN_PROCESO, then=Value(0)),
            When(
                estado__in=[Reserva.ESTADO_PROGRAMADA, Reserva.ESTADO_CONFIRMADA],
                then=Value(1),
            ),
            When(estado=Reserva.ESTADO_FINALIZADA, then=Value(2)),
            default=Value(3),
            output_field=IntegerField(),
        ),
        "fecha_inicio",
        "id",
    )


def _atajos_dashboard(filtros, resumen):
    definiciones = [
        ("todas", "Todas las citas", resumen["reservas_todas"]),
        ("hoy", "Reservas hoy", resumen["reservas_hoy"]),
        ("semana", "Semana actual", resumen["reservas_semana"]),
        ("mes", "Mes actual", resumen["reservas_mes"]),
        ("pendientes", "Pendientes de atencion", resumen["pendientes"]),
        ("historial", "Historial", resumen.get("reservas_historial", 0)),
    ]
    tarjetas = []
    for slug, label, value in definiciones:
        qs = _querystring_dashboard(filtros, atajo=slug)
        url = reverse("citas:dashboard")
        if qs:
            url = f"{url}?{qs}"
        tarjetas.append(
            {
                "slug": slug,
                "label": label,
                "value": value,
                "url": url,
                "is_active": filtros["atajo"] == slug,
            }
        )
    return tarjetas


def _redirect_admin_dashboard_target(request, *, default_view="citas:dashboard"):
    destino = (request.POST.get("next") or "").strip()
    if destino and destino.startswith("/citas/"):
        return redirect(destino)
    return redirect(default_view)


@admin_required_session
def dashboard(request):
    mantenimiento_reservas_dashboard(actor=_usuario_admin(request))
    filtros = _leer_filtros_dashboard(request)
    reservas = _aplicar_filtros_dashboard(_reservas_admin_queryset(), filtros)
    reservas = _ordenar_reservas_dashboard(reservas)
    resumen = resumen_dashboard_admin()
    ingresos_periodo_activo = resumen["ingresos_por_periodo"].get(
        filtros["atajo"] or "todas",
        resumen["ingresos_por_periodo"]["todas"],
    )

    return render(
        request,
        "citas/dashboard/dashboard.html",
        {
            "reservas": reservas,
            "reservas_total": reservas.count(),
            "profesionales": Profesional.objects.filter(activo=True),
            "estado_filtro": filtros["estado"],
            "profesional_id": filtros["profesional_id"],
            "asistencia": filtros["asistencia"],
            "query": filtros["q"],
            "atajo_activo": filtros["atajo"],
            "atajos_dashboard": _atajos_dashboard(filtros, resumen),
            "dashboard_return_url": request.get_full_path(),
            "estados_reserva": Reserva.ESTADOS,
            "horario_atencion": resumen_horario_atencion(),
            "ingresos_periodo_activo": ingresos_periodo_activo,
            **resumen,
        },
    )


@admin_required_session
def almanaque(request):
    mantenimiento_reservas_dashboard(actor=_usuario_admin(request))
    filtros = _leer_filtros_dashboard(request)
    reservas = _aplicar_filtros_dashboard(_reservas_admin_queryset(), filtros).order_by("fecha_inicio")
    resumen = resumen_dashboard_admin()

    return render(
        request,
        "citas/dashboard/calendario.html",
        {
            "reservas": reservas,
            "profesionales": Profesional.objects.filter(activo=True),
            "estado_filtro": filtros["estado"],
            "profesional_id": filtros["profesional_id"],
            "asistencia": filtros["asistencia"],
            "query": filtros["q"],
            "estados_reserva": Reserva.ESTADOS,
            "metodos_pago": PagoReserva.METODOS,
            "tipos_pago": PagoReserva.TIPOS,
            "productos_facturables": _productos_facturables(),
            "horario_atencion": resumen_horario_atencion(),
            **resumen,
        },
    )


@admin_required_session
def calendario(request):
    return almanaque(request)


@login_required_session
def agenda(request):
    usuario = _usuario_actual(request)
    reservas = reservas_visibles_para_usuario(usuario)
    estado = (request.GET.get("estado") or "").strip()
    if estado:
        reservas = reservas.filter(estado=estado)

    return render(
        request,
        "citas/public/lista.html",
        {
            "usuario": usuario,
            "reservas": reservas.order_by("-fecha_inicio"),
            "estado_filtro": estado,
            "estados_reserva": Reserva.ESTADOS,
        },
    )


@login_required_session
def reserva_nueva(request):
    usuario = _usuario_actual(request)
    servicios = Servicio.objects.select_related("profesional").filter(activo=True).order_by("nombre")
    servicio_preseleccionado = (request.GET.get("servicio") or "").strip()

    if request.method == "POST":
        try:
            servicio = get_object_or_404(Servicio.objects.select_related("profesional"), id=request.POST.get("servicio_id"), activo=True)
            fecha_inicio = _extraer_fecha_inicio_reserva(request)
            notas = request.POST.get("notas", "")

            pago_data = _extraer_pago_publico(request, servicio, requerido=False)
            reserva, pago = crear_reserva(
                cliente=usuario,
                servicio=servicio,
                fecha_inicio=fecha_inicio,
                notas=notas,
                origen=Reserva.ORIGEN_AUTENTICADO,
                actor=usuario,
                pago_data=pago_data,
            )
            messages.success(request, "La cita fue registrada correctamente.")
            if pago:
                messages.info(request, "El pago quedo registrado y la cita fue confirmada.")
            return redirect("citas:reserva_detalle", reserva_id=reserva.id)
        except ValidationError as exc:
            messages.error(request, exc.message if hasattr(exc, "message") else exc.messages[0])

    return render(
        request,
        "citas/public/form.html",
        _contexto_formulario_reserva(
            request=request,
            usuario=usuario,
            servicios=servicios,
            reserva=None,
            servicio_preseleccionado=servicio_preseleccionado,
        ),
    )


@login_required_session
def reserva_editar(request, reserva_id):
    reserva = get_object_or_404(
        Reserva.objects.select_related("cliente", "servicio", "servicio__profesional", "profesional"),
        id=reserva_id,
    )
    usuario = _asegurar_propiedad_reserva(request, reserva)
    if not puede_editar_reserva(reserva):
        messages.warning(request, "La cita ya no se puede editar.")
        return redirect("citas:reserva_detalle", reserva_id=reserva.id)

    if request.method == "POST":
        try:
            servicio = get_object_or_404(Servicio.objects.select_related("profesional"), id=request.POST.get("servicio_id"), activo=True)
            fecha_inicio = _extraer_fecha_inicio_reserva(request)
            actualizar_reserva(
                reserva=reserva,
                servicio=servicio,
                fecha_inicio=fecha_inicio,
                notas=request.POST.get("notas", ""),
                actor=usuario,
            )
            messages.success(request, "La cita fue actualizada correctamente.")
            return redirect("citas:reserva_detalle", reserva_id=reserva.id)
        except ValidationError as exc:
            messages.error(request, exc.message if hasattr(exc, "message") else exc.messages[0])
            # Mantener en la vista de edición si hay error

    servicios = Servicio.objects.select_related("profesional").filter(activo=True).order_by("nombre")
    return render(
        request,
        "citas/public/form.html",
        _contexto_formulario_reserva(
            request=request,
            usuario=usuario,
            servicios=servicios,
            reserva=reserva,
        ),
    )


@login_required_session
def reserva_detalle(request, reserva_id):
    reserva = get_object_or_404(
        Reserva.objects.select_related(
            "cliente", "servicio", "servicio__profesional", "profesional", "creada_por", "venta_asociada"
        )
        .prefetch_related("pagos", "historial_estados", "venta_asociada__detalles__producto"),
        id=reserva_id,
    )
    usuario = _asegurar_propiedad_reserva(request, reserva)
    return render(
        request,
        "citas/public/detalle.html",
        _construir_contexto_detalle_reserva(reserva, usuario),
    )


def _construir_contexto_detalle_reserva(reserva, usuario):
    """Construye el contexto para renderizar la vista de detalle de una reserva."""
    historial = reserva.historial_estados.select_related("usuario_actor").all()
    pagos = pagos_reserva_por_validos(reserva)
    venta_asociada = reserva.venta_asociada_segura
    venta_detalles = []
    if venta_asociada:
        for detalle in venta_asociada.detalles.select_related("producto").all():
            venta_detalles.append(
                {
                    "detalle": detalle,
                    "subtotal": detalle.cantidad * detalle.precio_unitario,
                }
            )
    return {
        "reserva": reserva,
        "usuario": usuario,
        "historial": historial,
        "pagos": pagos,
        "venta_asociada": venta_asociada,
        "venta_detalles": venta_detalles,
        "productos_facturables": _productos_facturables() if usuario.rol == Usuario.ROL_ADMIN else [],
        "horario_atencion": resumen_horario_atencion(),
        "metodos_pago": PagoReserva.METODOS,
        "tipos_pago": PagoReserva.TIPOS,
        "profesionales": Profesional.objects.filter(activo=True).order_by("nombre") if usuario.rol == Usuario.ROL_ADMIN else [],
        "puede_confirmar": _estado_puede_pasar_a(reserva, Reserva.ESTADO_CONFIRMADA),
        "puede_iniciar": _estado_puede_pasar_a(reserva, Reserva.ESTADO_EN_PROCESO),
        "puede_finalizar": _estado_puede_pasar_a(reserva, Reserva.ESTADO_FINALIZADA) and reserva.esta_pagada,
        "puede_cancelar_admin": _estado_puede_pasar_a(reserva, Reserva.ESTADO_CANCELADA),
        "puede_no_asistir": _estado_puede_pasar_a(reserva, Reserva.ESTADO_NO_ASISTIO),
        "puede_reasignar_profesional": usuario.rol == Usuario.ROL_ADMIN and reserva.estado not in {
            Reserva.ESTADO_FINALIZADA,
            Reserva.ESTADO_CANCELADA,
            Reserva.ESTADO_NO_ASISTIO,
        },
    }


@login_required_session
def reserva_cancelar(request, reserva_id):
    reserva = get_object_or_404(Reserva.objects.select_related("cliente"), id=reserva_id)
    usuario = _asegurar_propiedad_reserva(request, reserva)
    if request.method != "POST":
        return redirect("citas:reserva_detalle", reserva_id=reserva.id)

    try:
        observacion = request.POST.get("motivo_cancelacion", "Cancelada desde el modulo de citas.")
        cambiar_estado_reserva(
            reserva=reserva,
            nuevo_estado=Reserva.ESTADO_CANCELADA,
            actor=usuario,
            observacion=observacion,
        )
        messages.success(request, "La cita fue cancelada.")
    except ValidationError as exc:
        messages.error(request, exc.message if hasattr(exc, "message") else exc.messages[0])
    if usuario.rol == Usuario.ROL_ADMIN:
        return redirect("citas:calendario")
    return redirect("citas:agenda")


@admin_required_session
def reserva_actualizar_profesional(request, reserva_id):
    reserva = get_object_or_404(
        Reserva.objects.select_related("cliente", "servicio", "servicio__profesional", "profesional"),
        id=reserva_id,
    )
    usuario = _usuario_admin(request)
    if request.method != "POST":
        return redirect("citas:reserva_detalle", reserva_id=reserva.id)

    try:
        profesional = _extraer_profesional_desde_request(request)
        actualizar_profesional_reserva(
            reserva=reserva,
            profesional=profesional,
            actor=usuario,
        )
        messages.success(request, f"La cita ahora quedo asignada a {profesional.nombre}.")
    except ValidationError as exc:
        messages.error(request, exc.message if hasattr(exc, "message") else exc.messages[0])
    return redirect("citas:reserva_detalle", reserva_id=reserva.id)


@admin_required_session
def reserva_confirmar(request, reserva_id):
    reserva = get_object_or_404(Reserva, id=reserva_id)
    usuario = _usuario_admin(request)
    if request.method == "POST":
        try:
            cambiar_estado_reserva(
                reserva=reserva,
                nuevo_estado=Reserva.ESTADO_CONFIRMADA,
                actor=usuario,
                observacion="Cita confirmada desde dashboard.",
            )
            messages.success(request, "La cita fue confirmada.")
        except ValidationError as exc:
            messages.error(request, exc.message if hasattr(exc, "message") else exc.messages[0])
    return _redirect_admin_dashboard_target(request, default_view="citas:almanaque")


@admin_required_session
def reserva_iniciar(request, reserva_id):
    reserva = get_object_or_404(Reserva, id=reserva_id)
    usuario = _usuario_admin(request)
    if request.method == "POST":
        try:
            cambiar_estado_reserva(
                reserva=reserva,
                nuevo_estado=Reserva.ESTADO_EN_PROCESO,
                actor=usuario,
                observacion="Atencion iniciada.",
            )
            messages.success(request, "La cita paso a estado en proceso.")
        except ValidationError as exc:
            messages.error(request, exc.message if hasattr(exc, "message") else exc.messages[0])
    return _redirect_admin_dashboard_target(request, default_view="citas:almanaque")


@admin_required_session
def reserva_finalizar(request, reserva_id):
    reserva = get_object_or_404(Reserva, id=reserva_id)
    usuario = _usuario_admin(request)
    if request.method == "POST":
        try:
            cambiar_estado_reserva(
                reserva=reserva,
                nuevo_estado=Reserva.ESTADO_FINALIZADA,
                actor=usuario,
                observacion="Atencion finalizada.",
            )
            messages.success(request, "La cita fue finalizada.")
        except ValidationError as exc:
            messages.error(request, exc.message if hasattr(exc, "message") else exc.messages[0])
    return _redirect_admin_dashboard_target(request, default_view="citas:almanaque")


@admin_required_session
def reserva_no_asistio(request, reserva_id):
    reserva = get_object_or_404(Reserva, id=reserva_id)
    usuario = _usuario_admin(request)
    if request.method == "POST":
        try:
            cambiar_estado_reserva(
                reserva=reserva,
                nuevo_estado=Reserva.ESTADO_NO_ASISTIO,
                actor=usuario,
                observacion="Cliente marcado como no asistio.",
            )
            messages.success(request, "La cita fue marcada como no asistio.")
        except ValidationError as exc:
            messages.error(request, exc.message if hasattr(exc, "message") else exc.messages[0])
    return _redirect_admin_dashboard_target(request, default_view="citas:almanaque")


@login_required_session
def reserva_registrar_pago(request, reserva_id):
    reserva = get_object_or_404(
        Reserva.objects.select_related("cliente", "servicio", "servicio__profesional", "profesional"),
        id=reserva_id,
    )
    usuario = _asegurar_propiedad_reserva(request, reserva)
    if request.method != "POST":
        return redirect("citas:reserva_detalle", reserva_id=reserva.id)

    try:
        from apps.citas.services import registrar_pago

        es_admin = usuario.rol == Usuario.ROL_ADMIN
        venta = None
        total_productos = Decimal("0")
        if es_admin:
            pago_data = _extraer_pago_admin(request, reserva)
            productos_seleccionados = _extraer_productos_admin(request)
        else:
            pago_data = _extraer_pago_publico(
                request,
                reserva.servicio,
                requerido=True,
                monto=reserva.saldo_pendiente,
            )
            productos_seleccionados = []

        monto_pago = pago_data["monto"]
        if es_admin and monto_pago <= 0 and not productos_seleccionados:
            raise ValidationError("Debes registrar un pago o agregar al menos un producto para facturar.")

        with transaction.atomic():
            pago = None
            if monto_pago > 0:
                pago = registrar_pago(
                    reserva=reserva,
                    monto=monto_pago,
                    metodo_pago=pago_data["metodo_pago"],
                    referencia=pago_data.get("referencia", ""),
                    tipo=pago_data.get("tipo", PagoReserva.TIPO_TOTAL),
                    actor=usuario,
                )

            if es_admin and productos_seleccionados:
                venta, total_productos = registrar_venta_desde_reserva(
                    reserva=reserva,
                    items=productos_seleccionados,
                    metodo_pago=pago_data["metodo_pago"],
                    referencia_pago=pago_data.get("referencia", ""),
                    validado_por=usuario.id,
                )

            if pago and reserva.estado == Reserva.ESTADO_PROGRAMADA:
                cambiar_estado_reserva(
                    reserva=reserva,
                    nuevo_estado=Reserva.ESTADO_CONFIRMADA,
                    actor=usuario,
                    observacion="Pago registrado y cita confirmada.",
                )

        if pago and venta:
            messages.success(
                request,
                f"Se registraron el pago de la cita y {format_money(total_productos)} en productos dentro de la misma gestion.",
            )
        elif venta:
            messages.success(request, "La venta de productos fue registrada correctamente desde la cita.")
        else:
            messages.success(request, "El pago fue registrado correctamente.")
        if usuario.rol == Usuario.ROL_ADMIN:
            return redirect("citas:calendario")
        return redirect("citas:reserva_detalle", reserva_id=reserva.id)
    except ValidationError as exc:
        messages.error(request, exc.message if hasattr(exc, "message") else exc.messages[0])
        # Mantener en la misma vista de detalle cuando hay error
        reserva = get_object_or_404(
            Reserva.objects.select_related(
                "cliente", "servicio", "servicio__profesional", "profesional", "creada_por", "venta_asociada"
            )
            .prefetch_related("pagos", "historial_estados", "venta_asociada__detalles__producto"),
            id=reserva_id,
        )
        return render(
            request,
            "citas/public/detalle.html",
            _construir_contexto_detalle_reserva(reserva, usuario),
        )


def comprobante_pago_pdf(request, pago_id):
    pago = None
    token = (request.GET.get("token") or "").strip()
    if token:
        try:
            from apps.citas.services import resolver_token_comprobante

            pago = resolver_token_comprobante(token)
        except Exception:
            return HttpResponseForbidden("Token de comprobante invalido.")
        if pago.id != pago_id:
            return HttpResponseForbidden("El comprobante solicitado no coincide con el token.")
    else:
        usuario = _usuario_actual(request)
        if not usuario:
            return HttpResponseForbidden("Debes iniciar sesion para ver este comprobante.")
        pago = get_object_or_404(
            PagoReserva.objects.select_related(
                "reserva",
                "reserva__cliente",
                "reserva__servicio",
                "reserva__profesional",
            ),
            id=pago_id,
        )
        if usuario.rol != Usuario.ROL_ADMIN and pago.reserva.cliente_id != usuario.id:
            return HttpResponseForbidden("No tienes acceso a este comprobante.")

    if pago.estado != PagoReserva.ESTADO_CONFIRMADO:
        return HttpResponseForbidden("El pago no tiene un comprobante valido.")

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    y = height - 60
    pdf.setTitle(f"Comprobante {pago.numero_comprobante}")
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(50, y, "Comprobante de Pago de Cita")
    y -= 30
    pdf.setFont("Helvetica", 11)
    lineas = [
        f"Numero de comprobante: {pago.numero_comprobante}",
        f"Fecha de pago: {timezone.localtime(pago.fecha_pago).strftime('%d/%m/%Y %H:%M')}",
        f"Cliente: {pago.reserva.cliente_nombre_completo}",
        f"Servicio: {pago.reserva.servicio.nombre}",
        f"Profesional: {pago.reserva.profesional_reserva.nombre if pago.reserva.profesional_reserva else 'Sin asignar'}",
        f"Fecha de la cita: {timezone.localtime(pago.reserva.fecha_inicio).strftime('%d/%m/%Y %H:%M')}",
        f"Monto: {format_money(pago.monto)}",
        f"Metodo de pago: {pago.get_metodo_pago_display()}",
        f"Referencia: {pago.referencia or 'N/A'}",
        f"Estado: {pago.get_estado_display()}",
    ]
    venta_asociada = pago.reserva.venta_asociada_segura
    if venta_asociada:
        lineas.extend(
            [
                f"Productos asociados: {format_money(venta_asociada.total)}",
                f"Total factura mixta: {format_money(venta_asociada.total_factura)}",
            ]
        )
    for linea in lineas:
        pdf.drawString(50, y, linea)
        y -= 20

    if venta_asociada and venta_asociada.detalles.exists():
        y -= 5
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(50, y, "Detalle de productos:")
        y -= 20
        pdf.setFont("Helvetica", 10)
        for detalle in venta_asociada.detalles.select_related("producto").all():
            pdf.drawString(
                55,
                y,
                f"- {detalle.producto.nombre}: {detalle.cantidad} x {format_money(detalle.precio_unitario)}",
            )
            y -= 18

    y -= 10
    pdf.setFont("Helvetica-Oblique", 10)
    pdf.drawString(50, y, "Documento generado automaticamente por Lotus Dream Spa.")
    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    response = HttpResponse(buffer.read(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="comprobante-{pago.numero_comprobante}.pdf"'
    return response

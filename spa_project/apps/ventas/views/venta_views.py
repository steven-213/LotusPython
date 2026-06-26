import csv
from datetime import timedelta, datetime
from decimal import Decimal
from io import BytesIO
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Avg, Count, OuterRef, Prefetch, Q, Subquery, Sum
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.common.currency import format_money, parse_money
from apps.inventario.models import Producto
from apps.inventario.services import anotar_stock_disponible, descontar_stock, obtener_stock_disponible
from apps.sesiones.decorators import admin_required_session
from apps.sesiones.models import Usuario
from apps.ventas.models import DetalleVenta, SolicitudDevolucionVenta, ValidacionVenta, Venta
from apps.ventas.telegram_notifier import notificar_compra_pendiente


PANEL_TODAS = "todas"
PANEL_PAGOS_PENDIENTES = "pagos_pendientes"
PANEL_PAGOS_APROBADOS = "pagos_aprobados"
PANEL_PAGOS_RECHAZADOS = "pagos_rechazados"
PANEL_DEVOLUCIONES_PENDIENTES = "devoluciones_pendientes"
PANEL_DEVOLUCIONES_APROBADAS = "devoluciones_aprobadas"
PANEL_DEVOLUCIONES_RECHAZADAS = "devoluciones_rechazadas"
PERIODO_TODAS = "todas"
PERIODO_DIARIO = "diario"
PERIODO_SEMANAL = "semanal"
PERIODO_MENSUAL = "mensual"
MESES_VENTA = [
    (1, "Enero"),
    (2, "Febrero"),
    (3, "Marzo"),
    (4, "Abril"),
    (5, "Mayo"),
    (6, "Junio"),
    (7, "Julio"),
    (8, "Agosto"),
    (9, "Septiembre"),
    (10, "Octubre"),
    (11, "Noviembre"),
    (12, "Diciembre"),
]


def _resumir_productos_devueltos(solicitudes):
    productos = []
    for solicitud in solicitudes:
        nombre = solicitud.detalle_venta.producto.nombre
        if nombre not in productos:
            productos.append(nombre)
    if not productos:
        return "Sin devoluciones"
    if len(productos) == 1:
        return productos[0]
    if len(productos) == 2:
        return f"{productos[0]} y {productos[1]}"
    return f"{productos[0]}, {productos[1]} y {len(productos) - 2} mas"


def _resolver_resumen_devolucion_detalle(detalle, solicitudes):
    solicitudes = list(solicitudes)
    pendientes = [s for s in solicitudes if s.estado == SolicitudDevolucionVenta.ESTADO_PENDIENTE]
    aprobadas = [s for s in solicitudes if s.estado == SolicitudDevolucionVenta.ESTADO_APROBADA]
    rechazadas = [s for s in solicitudes if s.estado == SolicitudDevolucionVenta.ESTADO_RECHAZADA]

    cantidad_aprobada = sum(s.cantidad for s in aprobadas)

    if pendientes:
        return {
            "slug": "pendiente",
            "label": "En espera",
            "detail": f"{len(pendientes)} solicitud(es) del cliente",
        }
    if cantidad_aprobada >= detalle.cantidad and cantidad_aprobada > 0:
        return {
            "slug": "devuelta_total",
            "label": "Devuelta total",
            "detail": f"{cantidad_aprobada} unidad(es) aprobadas",
        }
    if cantidad_aprobada > 0:
        return {
            "slug": "devuelta_parcial",
            "label": "Devuelta parcial",
            "detail": f"{cantidad_aprobada} unidad(es) aprobadas",
        }
    if rechazadas:
        return {
            "slug": "rechazada",
            "label": "Rechazada",
            "detail": f"{len(rechazadas)} solicitud(es) rechazadas",
        }
    return {
        "slug": "sin_devolucion",
        "label": "Sin devolucion",
        "detail": "Sin solicitudes del cliente",
    }


def _resolver_resumen_devolucion_venta(venta):
    solicitudes = []
    total_items = 0
    total_aprobado = 0

    for detalle in venta.detalles.all():
        total_items += detalle.cantidad
        detalle_solicitudes = list(detalle.solicitudes_devolucion.all())
        solicitudes.extend(detalle_solicitudes)
        total_aprobado += sum(
            solicitud.cantidad
            for solicitud in detalle_solicitudes
            if solicitud.estado == SolicitudDevolucionVenta.ESTADO_APROBADA
        )

    pendientes = [s for s in solicitudes if s.estado == SolicitudDevolucionVenta.ESTADO_PENDIENTE]
    rechazadas = [s for s in solicitudes if s.estado == SolicitudDevolucionVenta.ESTADO_RECHAZADA]
    aprobadas = [s for s in solicitudes if s.estado == SolicitudDevolucionVenta.ESTADO_APROBADA]
    productos = _resumir_productos_devueltos(solicitudes)

    if pendientes:
        return {
            "slug": "pendiente",
            "label": "En espera",
            "detail": f"Cliente solicito devolucion de {productos}",
        }
    if total_aprobado >= total_items and total_aprobado > 0:
        return {
            "slug": "devuelta_total",
            "label": "Devuelta total",
            "detail": f"Devolucion aprobada de {productos}",
        }
    if aprobadas:
        return {
            "slug": "devuelta_parcial",
            "label": "Devuelta parcial",
            "detail": f"Devolucion aprobada de {productos}",
        }
    if rechazadas:
        return {
            "slug": "rechazada",
            "label": "Rechazada",
            "detail": f"Solicitud rechazada para {productos}",
        }
    return {
        "slug": "sin_devolucion",
        "label": "Sin devoluciones",
        "detail": "El cliente no ha solicitado devoluciones",
    }


def _resolver_estado_pago(validacion):
    if not validacion:
        return {
            "slug": "sin_validacion",
            "label": "Sin validar",
            "detail": "No hay validaciones registradas para esta venta.",
        }

    estado = (validacion.estado or "").strip().lower()
    if estado in {"comprado", "validada"}:
        return {
            "slug": "aprobado",
            "label": "Aprobado",
            "detail": "Pago confirmado en el sistema.",
        }
    if estado == "pendiente":
        return {
            "slug": "pendiente",
            "label": "Pendiente",
            "detail": "Pago aun por revisar.",
        }
    return {
        "slug": "rechazado",
        "label": "Rechazado",
        "detail": "Pago rechazado o sin aprobacion.",
    }


def _ventas_queryset():
    ultima_validacion = ValidacionVenta.objects.filter(venta_id=OuterRef("pk")).order_by(
        "-fecha_validacion",
        "-id",
    )
    return (
        Venta.objects.select_related("cliente", "reserva", "reserva__servicio")
        .annotate(ultimo_estado_pago=Subquery(ultima_validacion.values("estado")[:1]))
        .prefetch_related(
            Prefetch(
                "validaciones",
                queryset=ValidacionVenta.objects.order_by("-fecha_validacion", "-id"),
            ),
            "detalles__producto",
            "detalles__solicitudes_devolucion",
        )
        .order_by("-fecha")
    )


def _obtener_paneles_ventas():
    return {
        PANEL_TODAS: {
            "label": "Todas las ventas",
            "copy": "Ultimas ventas registradas en el sistema.",
        },
        PANEL_PAGOS_PENDIENTES: {
            "label": "Pagos pendientes",
            "copy": "Ventas que aun esperan validacion de pago.",
        },
        PANEL_PAGOS_APROBADOS: {
            "label": "Pagos aprobados",
            "copy": "Ventas con pago aprobado o confirmado.",
        },
        PANEL_PAGOS_RECHAZADOS: {
            "label": "Pagos rechazados",
            "copy": "Ventas cuyo pago fue rechazado.",
        },
        PANEL_DEVOLUCIONES_PENDIENTES: {
            "label": "Devoluciones pendientes",
            "copy": "Ventas con solicitudes de devolucion por responder.",
        },
        PANEL_DEVOLUCIONES_APROBADAS: {
            "label": "Devoluciones aprobadas",
            "copy": "Ventas con devoluciones ya aprobadas.",
        },
        PANEL_DEVOLUCIONES_RECHAZADAS: {
            "label": "Devoluciones rechazadas",
            "copy": "Ventas con solicitudes de devolucion rechazadas.",
        },
    }


def _obtener_periodos_ventas():
    hoy = timezone.localdate()
    inicio_semana = hoy - timedelta(days=hoy.weekday())
    return {
        PERIODO_TODAS: {
            "label": "Todas",
            "copy": "Todo el historial de ventas registrado.",
            "filters": {},
        },
        PERIODO_DIARIO: {
            "label": "Hoy",
            "copy": "Ventas registradas durante el dia actual.",
            "filters": {"fecha__date": hoy},
        },
        PERIODO_SEMANAL: {
            "label": "Esta semana",
            "copy": "Ventas acumuladas desde el lunes hasta hoy.",
            "filters": {
                "fecha__date__gte": inicio_semana,
                "fecha__date__lte": hoy,
            },
        },
        PERIODO_MENSUAL: {
            "label": "Este mes",
            "copy": "Ventas registradas en el mes actual.",
            "filters": {
                "fecha__year": hoy.year,
                "fecha__month": hoy.month,
            },
        },
    }


def _normalizar_numero_entero(valor, *, minimo=None, maximo=None):
    if valor in {"", None}:
        return ""
    try:
        numero = int(str(valor).strip())
    except (TypeError, ValueError):
        return ""

    if minimo is not None and numero < minimo:
        return ""
    if maximo is not None and numero > maximo:
        return ""
    return str(numero)


def _leer_filtros_ventas(request):
    panel = (request.GET.get("panel") or PANEL_TODAS).strip() or PANEL_TODAS
    if panel not in _obtener_paneles_ventas():
        panel = PANEL_TODAS
    periodo = (request.GET.get("periodo") or PERIODO_DIARIO).strip().lower()
    if periodo not in _obtener_periodos_ventas():
        periodo = PERIODO_DIARIO

    estado = (request.GET.get("estado") or "").strip().lower()
    if estado == "rechazada":
        estado = "rechazado"

    return {
        "panel": panel,
        "periodo": periodo,
        "q": (request.GET.get("q") or "").strip(),
        "cliente_id": (request.GET.get("cliente_id") or "").strip(),
        "estado": estado,
        "dia": _normalizar_numero_entero(request.GET.get("dia"), minimo=1, maximo=31),
        "mes": _normalizar_numero_entero(request.GET.get("mes"), minimo=1, maximo=12),
        "anio": _normalizar_numero_entero(request.GET.get("anio"), minimo=2000, maximo=2100),
        "export": (request.GET.get("export") or "").strip().lower(),
    }


def _aplicar_panel_ventas(queryset, panel):
    if panel == PANEL_PAGOS_PENDIENTES:
        return queryset.filter(ultimo_estado_pago__iexact="pendiente")
    if panel == PANEL_PAGOS_APROBADOS:
        return queryset.filter(
            Q(ultimo_estado_pago__iexact="comprado")
            | Q(ultimo_estado_pago__iexact="validada")
        )
    if panel == PANEL_PAGOS_RECHAZADOS:
        return queryset.filter(
            Q(ultimo_estado_pago__iexact="rechazado")
            | Q(ultimo_estado_pago__iexact="rechazada")
        )
    if panel == PANEL_DEVOLUCIONES_PENDIENTES:
        return queryset.filter(
            detalles__solicitudes_devolucion__estado=SolicitudDevolucionVenta.ESTADO_PENDIENTE
        ).distinct()
    if panel == PANEL_DEVOLUCIONES_APROBADAS:
        return queryset.filter(
            detalles__solicitudes_devolucion__estado=SolicitudDevolucionVenta.ESTADO_APROBADA
        ).distinct()
    if panel == PANEL_DEVOLUCIONES_RECHAZADAS:
        return queryset.filter(
            detalles__solicitudes_devolucion__estado=SolicitudDevolucionVenta.ESTADO_RECHAZADA
        ).distinct()
    return queryset


def _aplicar_periodo_ventas(queryset, periodo):
    periodo_info = _obtener_periodos_ventas().get(periodo) or _obtener_periodos_ventas()[PERIODO_DIARIO]
    return queryset.filter(**periodo_info["filters"])


def _aplicar_filtros_ventas(queryset, filtros):
    if filtros["q"]:
        queryset = queryset.filter(
            Q(cliente__nombre__icontains=filtros["q"])
            | Q(cliente__apellido__icontains=filtros["q"])
        )

    if filtros["cliente_id"]:
        queryset = queryset.filter(cliente_id=filtros["cliente_id"])

    if filtros["estado"] == "pendiente":
        queryset = queryset.filter(ultimo_estado_pago__iexact="pendiente")
    elif filtros["estado"] == "comprado":
        queryset = queryset.filter(
            Q(ultimo_estado_pago__iexact="comprado")
            | Q(ultimo_estado_pago__iexact="validada")
        )
    elif filtros["estado"] == "rechazado":
        queryset = queryset.filter(
            Q(ultimo_estado_pago__iexact="rechazado")
            | Q(ultimo_estado_pago__iexact="rechazada")
        )

    if filtros["dia"]:
        queryset = queryset.filter(fecha__day=int(filtros["dia"]))
    if filtros["mes"]:
        queryset = queryset.filter(fecha__month=int(filtros["mes"]))
    if filtros["anio"]:
        queryset = queryset.filter(fecha__year=int(filtros["anio"]))

    return queryset.distinct()


def _obtener_prioridad_devolucion(venta):
    """Retorna una tupla para ordenamiento: (prioridad_numerica, fecha_solicitud_reciente)
    Prioridad: 0 = pendiente (primero), 1 = aprobada/parcial, 2 = rechazada, 3 = sin devolucion
    """
    solicitudes = []
    for detalle in venta.detalles.all():
        solicitudes.extend(list(detalle.solicitudes_devolucion.all()))
    
    if not solicitudes:
        return (3, datetime.min)
    
    pendientes = [s for s in solicitudes if s.estado == SolicitudDevolucionVenta.ESTADO_PENDIENTE]
    aprobadas = [s for s in solicitudes if s.estado == SolicitudDevolucionVenta.ESTADO_APROBADA]
    rechazadas = [s for s in solicitudes if s.estado == SolicitudDevolucionVenta.ESTADO_RECHAZADA]
    
    if pendientes:
        fecha_mas_antigua = min(s.fecha_solicitud for s in pendientes)
        return (0, fecha_mas_antigua)
    
    if aprobadas:
        fecha_mas_antigua = min(s.fecha_solicitud for s in aprobadas)
        return (1, fecha_mas_antigua)
    
    if rechazadas:
        fecha_mas_antigua = min(s.fecha_solicitud for s in rechazadas)
        return (2, fecha_mas_antigua)
    
    return (3, datetime.min)


def _hidratar_ventas(ventas):
    for venta in ventas:
        validaciones = list(venta.validaciones.all())
        venta.validacion_reciente = validaciones[0] if validaciones else None
        venta.estado_pago_resumen = _resolver_estado_pago(venta.validacion_reciente)
        venta.devolucion_resumen = _resolver_resumen_devolucion_venta(venta)
    
    # Ordenar ventas priorizando las que tienen devoluciones pendientes
    ventas_ordenadas = sorted(ventas, key=_obtener_prioridad_devolucion)
    return ventas_ordenadas


def _querystring_ventas(filtros, **extras):
    params = {
        "panel": filtros.get("panel", PANEL_TODAS),
        "periodo": filtros.get("periodo", PERIODO_DIARIO),
        "q": filtros.get("q", ""),
        "cliente_id": filtros.get("cliente_id", ""),
        "estado": filtros.get("estado", ""),
        "dia": filtros.get("dia", ""),
        "mes": filtros.get("mes", ""),
        "anio": filtros.get("anio", ""),
    }
    params.update(extras)

    limpio = {}
    for key, value in params.items():
        if value in {"", None}:
            continue
        if key == "panel" and value == PANEL_TODAS:
            continue
        if key == "periodo" and value == PERIODO_DIARIO:
            continue
        limpio[key] = value

    if not limpio:
        return ""

    return urlencode(limpio)


def _exportar_ventas_excel(ventas):
    response = HttpResponse(content_type="application/vnd.ms-excel; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="listado_ventas.xls"'
    writer = csv.writer(response, delimiter="\t")
    writer.writerow(["ID", "Cliente", "Fecha", "Total", "Estado de pago", "Estado de devolucion"])
    for venta in ventas:
        writer.writerow(
            [
                venta.id,
                venta.cliente_nombre_completo,
                venta.fecha.strftime("%d/%m/%Y %H:%M"),
                str(venta.total),
                venta.estado_pago_resumen["label"],
                venta.devolucion_resumen["label"],
            ]
        )
    return response


def _exportar_ventas_pdf(ventas, titulo):
    buffer = BytesIO()
    documento = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        leftMargin=18,
        rightMargin=18,
        topMargin=18,
        bottomMargin=18,
    )
    estilos = getSampleStyleSheet()
    elementos = [Paragraph(titulo, estilos["Title"]), Spacer(1, 12)]
    data = [["ID", "Cliente", "Fecha", "Total", "Pago", "Devolucion"]]

    for venta in ventas:
        data.append(
            [
                f"#{venta.id}",
                venta.cliente_nombre_completo,
                venta.fecha.strftime("%d/%m/%Y %H:%M"),
                str(venta.total),
                venta.estado_pago_resumen["label"],
                venta.devolucion_resumen["label"],
            ]
        )

    tabla = Table(data, repeatRows=1, colWidths=[48, 160, 92, 80, 86, 125])
    tabla.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ca6b86")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e7cddb")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fff7fa")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elementos.append(tabla)
    documento.build(elementos)

    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="listado_ventas.pdf"'
    return response


def _obtener_productos_para_venta():
    return anotar_stock_disponible(Producto.objects.filter(activo=True)).filter(
        stock_disponible__gt=0
    ).order_by("nombre")


def _obtener_detalles_venta_desde_post(request):
    productos_ids = request.POST.getlist("producto_ids[]")
    cantidades = request.POST.getlist("cantidades[]")
    total_filas = max(len(productos_ids), len(cantidades), 0)
    productos_acumulados = {}

    for index in range(total_filas):
        producto_id = (productos_ids[index] if index < len(productos_ids) else "").strip()
        cantidad_raw = (cantidades[index] if index < len(cantidades) else "").strip()

        if not producto_id and not cantidad_raw:
            continue

        fila = index + 1
        if not producto_id:
            raise ValueError(f"Selecciona un producto en la fila {fila}.")

        try:
            cantidad = int(cantidad_raw)
        except (TypeError, ValueError):
            raise ValueError(f"La cantidad de la fila {fila} no es valida.")

        if cantidad <= 0:
            raise ValueError(f"La cantidad de la fila {fila} debe ser mayor a cero.")

        producto = Producto.objects.filter(id=producto_id, activo=True).first()
        if not producto:
            raise ValueError(f"El producto de la fila {fila} no existe o esta inactivo.")

        stock_disponible = obtener_stock_disponible(producto)
        acumulado = productos_acumulados.get(producto.id, {"producto": producto, "cantidad": 0})
        acumulado["cantidad"] += cantidad
        if acumulado["cantidad"] > stock_disponible:
            raise ValueError(
                f"Solo hay {stock_disponible} unidad(es) disponibles de {producto.nombre}."
            )
        productos_acumulados[producto.id] = acumulado

    detalles = list(productos_acumulados.values())
    if not detalles:
        raise ValueError("Agrega al menos un producto a la venta.")
    return detalles


def _obtener_resumen_ventas_por_periodo():
    """Calcula resúmenes de ventas para los períodos: diario, semanal y mensual."""
    hoy = timezone.localdate()
    inicio_semana = hoy - timedelta(days=hoy.weekday())
    
    # Período diario (últimas 24 horas)
    ventas_todas = Venta.objects.aggregate(
        total_monto=Sum("total"),
        total_ventas=Count("id"),
        promedio=Avg("total"),
    )
    ventas_diarias = Venta.objects.filter(fecha__date=hoy).aggregate(
        total_monto=Sum("total"),
        total_ventas=Count("id"),
        promedio=Avg("total"),
    )
    
    # Período semanal (últimos 7 días)
    ventas_semanales = Venta.objects.filter(
        fecha__date__gte=inicio_semana,
        fecha__date__lte=hoy,
    ).aggregate(
        total_monto=Sum("total"),
        total_ventas=Count("id"),
        promedio=Avg("total"),
    )
    
    # Período mensual (últimos 30 días)
    ventas_mensuales = Venta.objects.filter(
        fecha__year=hoy.year,
        fecha__month=hoy.month,
    ).aggregate(
        total_monto=Sum("total"),
        total_ventas=Count("id"),
        promedio=Avg("total"),
    )
    
    return {
        "todas": {
            "label": "Todas",
            "monto_total": format_money(ventas_todas["total_monto"] or Decimal(0)),
            "total_ventas": ventas_todas["total_ventas"] or 0,
            "promedio": format_money(ventas_todas["promedio"] or Decimal(0)),
        },
        "diario": {
            "label": "Hoy",
            "monto_total": format_money(ventas_diarias["total_monto"] or Decimal(0)),
            "total_ventas": ventas_diarias["total_ventas"] or 0,
            "promedio": format_money(ventas_diarias["promedio"] or Decimal(0)),
        },
        "semanal": {
            "label": "Esta semana",
            "monto_total": format_money(ventas_semanales["total_monto"] or Decimal(0)),
            "total_ventas": ventas_semanales["total_ventas"] or 0,
            "promedio": format_money(ventas_semanales["promedio"] or Decimal(0)),
        },
        "mensual": {
            "label": "Este mes",
            "monto_total": format_money(ventas_mensuales["total_monto"] or Decimal(0)),
            "total_ventas": ventas_mensuales["total_ventas"] or 0,
            "promedio": format_money(ventas_mensuales["promedio"] or Decimal(0)),
        },
    }


@admin_required_session
def venta_lista(request):
    filtros = _leer_filtros_ventas(request)
    paneles = _obtener_paneles_ventas()
    panel_actual = filtros["panel"]
    periodo_actual = filtros["periodo"]
    periodos_base = _obtener_periodos_ventas()
    resumen_periodos = _obtener_resumen_ventas_por_periodo()
    for periodo, info in periodos_base.items():
        resumen_periodos[periodo]["copy"] = info["copy"]
    periodo_info = resumen_periodos[periodo_actual]

    ventas_periodo = _aplicar_periodo_ventas(_ventas_queryset(), periodo_actual)
    ventas_filtradas = _aplicar_panel_ventas(ventas_periodo, panel_actual)
    ventas_filtradas = _aplicar_filtros_ventas(ventas_filtradas, filtros)
    ventas_total = ventas_filtradas.count()
    ventas = _hidratar_ventas(list(ventas_filtradas))

    if filtros["export"] == "excel":
        return _exportar_ventas_excel(ventas)
    if filtros["export"] == "pdf":
        return _exportar_ventas_pdf(
            ventas,
            f"Ventas - {periodo_info['label']} - {paneles[panel_actual]['label']}",
        )

    resumen_global = Venta.objects.aggregate(
        total_ventas=Count("id"),
        monto_total=Sum("total"),
        promedio_venta=Avg("total"),
    )
    ventas_anotadas = Venta.objects.annotate(
        ultimo_estado_pago=Subquery(
            ValidacionVenta.objects.filter(venta_id=OuterRef("pk"))
            .order_by("-fecha_validacion", "-id")
            .values("estado")[:1]
        )
    )
    validaciones_pendientes = ventas_anotadas.filter(ultimo_estado_pago__iexact="pendiente").count()
    validaciones_comprado = ventas_anotadas.filter(
        Q(ultimo_estado_pago__iexact="comprado") | Q(ultimo_estado_pago__iexact="validada")
    ).count()
    validaciones_rechazado = ventas_anotadas.filter(
        Q(ultimo_estado_pago__iexact="rechazado") | Q(ultimo_estado_pago__iexact="rechazada")
    ).count()
    devoluciones_pendientes = SolicitudDevolucionVenta.objects.filter(
        estado=SolicitudDevolucionVenta.ESTADO_PENDIENTE
    ).count()
    devoluciones_aprobadas = SolicitudDevolucionVenta.objects.filter(
        estado=SolicitudDevolucionVenta.ESTADO_APROBADA
    ).count()
    devoluciones_rechazadas = SolicitudDevolucionVenta.objects.filter(
        estado=SolicitudDevolucionVenta.ESTADO_RECHAZADA
    ).count()

    panel_nav = [
        {
            "panel": PANEL_TODAS,
            "label": "Todas",
            "value": ventas_periodo.count(),
            "meta": "Historial completo del periodo.",
        },
        {
            "panel": PANEL_PAGOS_PENDIENTES,
            "label": "Pagos pendientes",
            "value": _aplicar_panel_ventas(ventas_periodo, PANEL_PAGOS_PENDIENTES).count(),
            "meta": "Esperan revision de pago.",
        },
        {
            "panel": PANEL_PAGOS_APROBADOS,
            "label": "Pagos aprobados",
            "value": _aplicar_panel_ventas(ventas_periodo, PANEL_PAGOS_APROBADOS).count(),
            "meta": "Pago confirmado en el periodo.",
        },
        {
            "panel": PANEL_PAGOS_RECHAZADOS,
            "label": "Pagos rechazados",
            "value": _aplicar_panel_ventas(ventas_periodo, PANEL_PAGOS_RECHAZADOS).count(),
            "meta": "Pagos rechazados en el periodo.",
        },
        {
            "panel": PANEL_DEVOLUCIONES_PENDIENTES,
            "label": "Devoluciones pendientes",
            "value": _aplicar_panel_ventas(ventas_periodo, PANEL_DEVOLUCIONES_PENDIENTES).count(),
            "meta": "Clientes esperando respuesta.",
        },
        {
            "panel": PANEL_DEVOLUCIONES_APROBADAS,
            "label": "Devoluciones aprobadas",
            "value": _aplicar_panel_ventas(ventas_periodo, PANEL_DEVOLUCIONES_APROBADAS).count(),
            "meta": "Devoluciones aceptadas.",
        },
        {
            "panel": PANEL_DEVOLUCIONES_RECHAZADAS,
            "label": "Devoluciones rechazadas",
            "value": _aplicar_panel_ventas(ventas_periodo, PANEL_DEVOLUCIONES_RECHAZADAS).count(),
            "meta": "Devoluciones no aprobadas.",
        },
    ]
    for item in panel_nav:
        item["is_active"] = item["panel"] == panel_actual
        item_qs = _querystring_ventas(filtros, panel=item["panel"], export="")
        item["url"] = reverse("ventas:venta_lista")
        if item_qs:
            item["url"] = f"{item['url']}?{item_qs}#ventas-listado"
        else:
            item["url"] = f"{item['url']}#ventas-listado"

    periodos_nav = []
    for periodo, info in resumen_periodos.items():
        periodo_qs = _querystring_ventas(
            filtros,
            periodo=periodo,
            dia="",
            mes="",
            anio="",
            export="",
        )
        periodo_url = reverse("ventas:venta_lista")
        if periodo_qs:
            periodo_url = f"{periodo_url}?{periodo_qs}#ventas-listado"
        else:
            periodo_url = f"{periodo_url}#ventas-listado"
        periodos_nav.append(
            {
                "slug": periodo,
                "label": info["label"],
                "url": periodo_url,
                "is_active": periodo == periodo_actual,
            }
        )

    filtros_base = {key: value for key, value in filtros.items() if key != "export"}
    excel_qs = _querystring_ventas(filtros_base, export="excel")
    pdf_qs = _querystring_ventas(filtros_base, export="pdf")
    limpiar_qs = _querystring_ventas(
        {
            "panel": panel_actual,
            "periodo": periodo_actual,
        }
    )
    excel_url = reverse("ventas:venta_lista")
    pdf_url = reverse("ventas:venta_lista")
    limpiar_url = reverse("ventas:venta_lista")
    if excel_qs:
        excel_url = f"{excel_url}?{excel_qs}"
    else:
        excel_url = f"{excel_url}?export=excel"
    if pdf_qs:
        pdf_url = f"{pdf_url}?{pdf_qs}"
    else:
        pdf_url = f"{pdf_url}?export=pdf"
    if limpiar_qs:
        limpiar_url = f"{limpiar_url}?{limpiar_qs}#ventas-listado"
    else:
        limpiar_url = f"{limpiar_url}#ventas-listado"

    context = {
        "ventas": ventas,
        "ventas_total": ventas_total,
        "panel_actual": panel_actual,
        "panel_info": paneles[panel_actual],
        "periodo_actual": periodo_actual,
        "periodo_info": periodo_info,
        "periodos_nav": periodos_nav,
        "panel_nav": panel_nav,
        "monto_total": format_money(resumen_global["monto_total"] or Decimal(0)),
        "promedio_venta": format_money(resumen_global["promedio_venta"] or Decimal(0)),
        "clientes_unicos": Venta.objects.exclude(cliente_id__isnull=True).values("cliente_id").distinct().count(),
        "resumen_periodos": resumen_periodos,
        "clientes": Usuario.objects.filter(rol=Usuario.ROL_CLIENTE).order_by("nombre", "apellido"),
        "query": filtros["q"],
        "cliente_id": filtros["cliente_id"],
        "estado_filtro": filtros["estado"],
        "dia": filtros["dia"],
        "mes": filtros["mes"],
        "anio": filtros["anio"],
        "dias_disponibles": list(range(1, 32)),
        "meses_disponibles": MESES_VENTA,
        "anios_disponibles": list(
            range(timezone.localdate().year + 1, timezone.localdate().year - 3, -1)
        ),
        "excel_url": excel_url,
        "pdf_url": pdf_url,
        "limpiar_url": limpiar_url,
        "kpi_validaciones_pendientes": validaciones_pendientes,
        "kpi_validaciones_comprado": validaciones_comprado,
        "kpi_validaciones_rechazado": validaciones_rechazado,
        "kpi_devoluciones_pendientes": devoluciones_pendientes,
        "kpi_devoluciones_aprobadas": devoluciones_aprobadas,
        "kpi_devoluciones_rechazadas": devoluciones_rechazadas,
    }
    return render(request, "ventas/dashboard/lista.html", context)


@admin_required_session
def venta_nueva(request):
    clientes = Usuario.objects.filter(rol=Usuario.ROL_CLIENTE).order_by("nombre", "apellido")
    productos = _obtener_productos_para_venta()

    if request.method == "POST":
        cliente_id = (request.POST.get("cliente_id") or "").strip()
        if not cliente_id:
            messages.error(request, "Debes seleccionar un cliente.")
            return render(
                request,
                "ventas/dashboard/nueva.html",
                {"clientes": clientes, "productos": productos},
            )

        cliente = Usuario.objects.filter(id=cliente_id, rol=Usuario.ROL_CLIENTE).first()
        if not cliente:
            messages.error(request, "El cliente seleccionado no es valido.")
            return render(
                request,
                "ventas/dashboard/nueva.html",
                {"clientes": clientes, "productos": productos},
            )

        try:
            detalles = _obtener_detalles_venta_desde_post(request)
        except ValueError as exc:
            messages.error(request, str(exc))
            return render(
                request,
                "ventas/dashboard/nueva.html",
                {"clientes": clientes, "productos": productos},
            )

        total = sum(
            (detalle["producto"].precio_venta * detalle["cantidad"] for detalle in detalles),
            Decimal("0"),
        )

        with transaction.atomic():
            venta = Venta.objects.create(cliente=cliente, total=total)
            for detalle in detalles:
                DetalleVenta.objects.create(
                    venta=venta,
                    producto=detalle["producto"],
                    cantidad=detalle["cantidad"],
                    precio_unitario=detalle["producto"].precio_venta,
                )

            ValidacionVenta.objects.create(
                venta=venta,
                cliente=cliente,
                monto=total,
                estado="pendiente",
                observaciones="Venta creada desde el panel admin.",
            )

        messages.success(request, "La venta fue creada con sus productos y validacion pendiente.")
        return redirect("ventas:venta_detalle", venta_id=venta.id)

    return render(
        request,
        "ventas/dashboard/nueva.html",
        {"clientes": clientes, "productos": productos},
    )


@admin_required_session
def venta_detalle(request, venta_id):
    venta = get_object_or_404(
        Venta.objects.select_related("cliente", "reserva", "reserva__servicio").prefetch_related(
            "detalles__producto",
            "detalles__solicitudes_devolucion",
        ),
        id=venta_id,
    )
    validacion_reciente = venta.validaciones.order_by("-fecha_validacion", "-id").first()
    detalles_venta = []
    devoluciones_cliente = []

    for detalle in venta.detalles.all():
        solicitudes = list(detalle.solicitudes_devolucion.all().order_by("-fecha_solicitud", "-id"))
        devoluciones_cliente.extend(solicitudes)
        detalles_venta.append(
            {
                "detalle": detalle,
                "subtotal": detalle.cantidad * detalle.precio_unitario,
                "devolucion_resumen": _resolver_resumen_devolucion_detalle(detalle, solicitudes),
                "solicitudes": solicitudes,
            }
        )

    context = {
        "venta": venta,
        "validacion_reciente": validacion_reciente,
        "detalles_venta": detalles_venta,
        "reserva_asociada": venta.reserva,
        "devoluciones_cliente": sorted(
            devoluciones_cliente,
            key=lambda solicitud: (solicitud.fecha_solicitud, solicitud.id),
            reverse=True,
        ),
        "devolucion_resumen": _resolver_resumen_devolucion_venta(venta),
    }
    return render(request, "ventas/dashboard/detalle.html", context)


@admin_required_session
def venta_validaciones(request, venta_id):
    venta = get_object_or_404(Venta, id=venta_id)
    cliente = venta.cliente
    if request.method == "POST":
        validacion = venta.validaciones.order_by("-fecha_validacion").first()

        if validacion:
            validacion.metodo_pago = request.POST.get("metodo_pago", "")
            validacion.referencia_pago = request.POST.get("referencia_pago", "")
            validacion.monto = parse_money(request.POST.get("monto"))
            nuevo_estado = request.POST.get("estado", "pendiente")
            validacion.estado = nuevo_estado
            validacion.cliente = cliente
            validacion.validado_por = request.session.get("usuario_id")
            validacion.observaciones = request.POST.get("observaciones", "")
            validacion.save()

            if nuevo_estado == "pendiente":
                sent = notificar_compra_pendiente(venta=venta, validacion=validacion)
                if not sent:
                    messages.warning(
                        request,
                        "La validacion quedo pendiente, pero fallo el envio a Telegram.",
                    )
        else:
            ValidacionVenta.objects.create(
                venta=venta,
                cliente=cliente,
                metodo_pago=request.POST.get("metodo_pago", ""),
                referencia_pago=request.POST.get("referencia_pago", ""),
                monto=parse_money(request.POST.get("monto")),
                estado=request.POST.get("estado", "pendiente"),
                validado_por=request.session.get("usuario_id"),
                observaciones=request.POST.get("observaciones", ""),
            )

        messages.success(request, "Validacion registrada correctamente")
        return redirect("ventas:venta_validaciones", venta_id=venta.id)

    context = {
        "venta": venta,
        "validaciones": venta.validaciones.all(),
        "validaciones_pendientes": ValidacionVenta.objects.filter(estado="pendiente").count(),
        "validaciones_comprado": ValidacionVenta.objects.filter(estado="comprado").count(),
        "validaciones_rechazado": ValidacionVenta.objects.filter(estado="rechazado").count(),
    }
    return render(request, "ventas/dashboard/validaciones.html", context)


def confirmar_compra_telegram(request, validacion_id):
    token = request.GET.get("token", "")
    if token != getattr(settings, "TELEGRAM_CONFIRM_TOKEN", ""):
        return HttpResponseForbidden("Token invalido.")

    validacion = get_object_or_404(ValidacionVenta, id=validacion_id)
    if validacion.estado == "comprado":
        return HttpResponse("La compra ya esta confirmada.")

    detalles = list(validacion.venta.detalles.select_related("producto").all())
    cantidades_por_producto = {}
    productos = {}
    for detalle in detalles:
        cantidades_por_producto[detalle.producto_id] = (
            cantidades_por_producto.get(detalle.producto_id, 0) + detalle.cantidad
        )
        productos[detalle.producto_id] = detalle.producto

    for producto_id, cantidad_total in cantidades_por_producto.items():
        producto = productos[producto_id]
        if obtener_stock_disponible(producto) < cantidad_total:
            return HttpResponse(
                f"No se pudo confirmar: stock insuficiente para {producto.nombre}."
            )

    with transaction.atomic():
        for producto_id, cantidad_total in cantidades_por_producto.items():
            descontar_stock(productos[producto_id], cantidad_total)

        validacion.estado = "comprado"
        validacion.observaciones = "Confirmado"
        validacion.save(update_fields=["estado", "observaciones"])

    return HttpResponse("Compra confirmada correctamente.")


def rechazar_compra_telegram(request, validacion_id):
    token = request.GET.get("token", "")
    if token != getattr(settings, "TELEGRAM_CONFIRM_TOKEN", ""):
        return HttpResponseForbidden("Token invalido.")

    validacion = get_object_or_404(ValidacionVenta, id=validacion_id)
    validacion.estado = "rechazado"
    validacion.observaciones = "Rechazado"
    validacion.save(update_fields=["estado", "observaciones"])
    return HttpResponse("Compra rechazada correctamente.")


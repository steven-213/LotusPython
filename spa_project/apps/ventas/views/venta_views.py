import csv
from datetime import datetime
from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Avg, Count, OuterRef, Prefetch, Q, Subquery, Sum
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

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
        Venta.objects.select_related("cliente", "cliente_invitado", "reserva", "reserva__servicio")
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

    estado = (request.GET.get("estado") or "").strip().lower()
    if estado == "rechazada":
        estado = "rechazado"

    return {
        "panel": panel,
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


def _aplicar_filtros_ventas(queryset, filtros):
    if filtros["q"]:
        queryset = queryset.filter(
            Q(cliente__nombre__icontains=filtros["q"])
            | Q(cliente__apellido__icontains=filtros["q"])
            | Q(cliente_invitado__nombre__icontains=filtros["q"])
            | Q(cliente_invitado__apellido__icontains=filtros["q"])
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


def _hidratar_ventas(ventas):
    for venta in ventas:
        validaciones = list(venta.validaciones.all())
        venta.validacion_reciente = validaciones[0] if validaciones else None
        venta.estado_pago_resumen = _resolver_estado_pago(venta.validacion_reciente)
        venta.devolucion_resumen = _resolver_resumen_devolucion_venta(venta)
    return ventas


def _querystring_ventas(filtros, **extras):
    params = {
        "panel": filtros.get("panel", PANEL_TODAS),
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
        limpio[key] = value

    if not limpio:
        return ""

    return "&".join(f"{key}={value}" for key, value in limpio.items())


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


@admin_required_session
def venta_lista(request):
    filtros = _leer_filtros_ventas(request)
    paneles = _obtener_paneles_ventas()
    panel_actual = filtros["panel"]

    ventas_panel = _aplicar_panel_ventas(_ventas_queryset(), panel_actual)
    total_panel = ventas_panel.count()
    ventas_preview = _hidratar_ventas(list(ventas_panel[:6]))

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

    cards = [
        {
            "panel": PANEL_TODAS,
            "label": "Total de ventas",
            "value": resumen_global["total_ventas"] or 0,
            "meta": "Operaciones registradas en el historial.",
            "icon": "bi bi-receipt-cutoff",
        },
        {
            "panel": PANEL_PAGOS_PENDIENTES,
            "label": "Pagos pendientes",
            "value": validaciones_pendientes,
            "meta": "Ventas que aun necesitan validacion.",
            "icon": "bi bi-clock-history",
        },
        {
            "panel": PANEL_PAGOS_APROBADOS,
            "label": "Pagos aprobados",
            "value": validaciones_comprado,
            "meta": "Ventas con pago ya confirmado.",
            "icon": "bi bi-check-circle",
        },
        {
            "panel": PANEL_PAGOS_RECHAZADOS,
            "label": "Pagos rechazados",
            "value": validaciones_rechazado,
            "meta": "Ventas con pago rechazado.",
            "icon": "bi bi-x-circle",
        },
        {
            "panel": PANEL_DEVOLUCIONES_PENDIENTES,
            "label": "Devoluciones pendientes",
            "value": devoluciones_pendientes,
            "meta": "Solicitudes de clientes pendientes.",
            "icon": "bi bi-arrow-counterclockwise",
        },
        {
            "panel": PANEL_DEVOLUCIONES_APROBADAS,
            "label": "Devoluciones aprobadas",
            "value": devoluciones_aprobadas,
            "meta": "Solicitudes resueltas favorablemente.",
            "icon": "bi bi-arrow-repeat",
        },
        {
            "panel": PANEL_DEVOLUCIONES_RECHAZADAS,
            "label": "Devoluciones rechazadas",
            "value": devoluciones_rechazadas,
            "meta": "Solicitudes cerradas sin aprobacion.",
            "icon": "bi bi-slash-circle",
        },
    ]
    for card in cards:
        card["is_active"] = card["panel"] == panel_actual
        card["url"] = reverse("ventas:venta_lista")
        if card["panel"] != PANEL_TODAS:
            card["url"] += f"?panel={card['panel']}"

    listado_qs = _querystring_ventas({"panel": panel_actual})
    listado_url = reverse("ventas:venta_listado")
    if listado_qs:
        listado_url = f"{listado_url}?{listado_qs}"

    context = {
        "cards": cards,
        "panel_actual": panel_actual,
        "panel_info": paneles[panel_actual],
        "ventas_preview": ventas_preview,
        "ventas_preview_total": total_panel,
        "listado_url": listado_url,
        "monto_total": format_money(resumen_global["monto_total"] or Decimal(0)),
        "promedio_venta": format_money(resumen_global["promedio_venta"] or Decimal(0)),
        "clientes_unicos": Venta.objects.exclude(cliente_id__isnull=True).values("cliente_id").distinct().count(),
    }
    return render(request, "ventas/dashboard/lista.html", context)


@admin_required_session
def venta_listado(request):
    filtros = _leer_filtros_ventas(request)
    paneles = _obtener_paneles_ventas()
    panel_actual = filtros["panel"]

    ventas_filtradas = _aplicar_panel_ventas(_ventas_queryset(), panel_actual)
    ventas_filtradas = _aplicar_filtros_ventas(ventas_filtradas, filtros)
    ventas = _hidratar_ventas(list(ventas_filtradas))

    if filtros["export"] == "excel":
        return _exportar_ventas_excel(ventas)
    if filtros["export"] == "pdf":
        return _exportar_ventas_pdf(ventas, f"Listado de ventas - {paneles[panel_actual]['label']}")

    filtros_base = {key: value for key, value in filtros.items() if key != "export"}
    excel_qs = _querystring_ventas(filtros_base, export="excel")
    pdf_qs = _querystring_ventas(filtros_base, export="pdf")

    context = {
        "ventas": ventas,
        "clientes": Usuario.objects.filter(rol=Usuario.ROL_CLIENTE).order_by("nombre", "apellido"),
        "panel_actual": panel_actual,
        "panel_info": paneles[panel_actual],
        "query": filtros["q"],
        "cliente_id": filtros["cliente_id"],
        "estado_filtro": filtros["estado"],
        "dia": filtros["dia"],
        "mes": filtros["mes"],
        "anio": filtros["anio"],
        "dias_disponibles": list(range(1, 32)),
        "meses_disponibles": MESES_VENTA,
        "anios_disponibles": list(range(datetime.now().year + 1, datetime.now().year - 3, -1)),
        "excel_url": f"{reverse('ventas:venta_listado')}?{excel_qs}" if excel_qs else f"{reverse('ventas:venta_listado')}?export=excel",
        "pdf_url": f"{reverse('ventas:venta_listado')}?{pdf_qs}" if pdf_qs else f"{reverse('ventas:venta_listado')}?export=pdf",
    }
    return render(request, "ventas/dashboard/listado_ventas.html", context)


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
        Venta.objects.select_related("cliente", "cliente_invitado", "reserva", "reserva__servicio").prefetch_related(
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
    cliente_invitado = venta.cliente_invitado
    if request.method == "POST":
        validacion = venta.validaciones.order_by("-fecha_validacion").first()

        if validacion:
            validacion.metodo_pago = request.POST.get("metodo_pago", "")
            validacion.referencia_pago = request.POST.get("referencia_pago", "")
            validacion.monto = parse_money(request.POST.get("monto"))
            nuevo_estado = request.POST.get("estado", "pendiente")
            validacion.estado = nuevo_estado
            validacion.cliente = cliente
            validacion.cliente_invitado = cliente_invitado
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
                cliente_invitado=cliente_invitado,
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


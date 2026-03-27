from datetime import datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Avg, Q, Sum
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from apps.common.currency import format_money, parse_money
from apps.inventario.services import descontar_stock, obtener_stock_disponible
from apps.sesiones.decorators import admin_required_session
from apps.sesiones.models import Usuario
from apps.ventas.models import ValidacionVenta, Venta
from apps.ventas.telegram_notifier import notificar_compra_pendiente


@admin_required_session
def venta_lista(request):
    query = request.GET.get("q", "")
    fecha_inicio = request.GET.get("fecha_inicio", "")
    fecha_fin = request.GET.get("fecha_fin", "")
    estado_filtro = request.GET.get("estado", "")
    cliente_id = request.GET.get("cliente_id", "")

    filtro_fecha = Q()
    if fecha_inicio:
        try:
            filtro_fecha &= Q(fecha__gte=datetime.strptime(fecha_inicio, "%Y-%m-%d"))
        except ValueError:
            fecha_inicio = ""
    if fecha_fin:
        try:
            filtro_fecha &= Q(fecha__lte=datetime.strptime(fecha_fin, "%Y-%m-%d") + timedelta(days=1))
        except ValueError:
            fecha_fin = ""

    ventas = Venta.objects.select_related("cliente").order_by("-fecha")
    if query:
        ventas = ventas.filter(cliente__nombre__icontains=query)
    if cliente_id:
        ventas = ventas.filter(cliente_id=cliente_id)
    if estado_filtro:
        venta_ids = ValidacionVenta.objects.filter(estado__iexact=estado_filtro).values_list(
            "venta_id",
            flat=True,
        )
        ventas = ventas.filter(id__in=venta_ids)
    if filtro_fecha:
        ventas = ventas.filter(filtro_fecha)

    for venta in ventas:
        venta.validacion_reciente = venta.validaciones.order_by("-fecha_validacion", "-id").first()

    monto_total = Venta.objects.aggregate(Sum("total"))["total__sum"] or Decimal(0)
    promedio_venta = Venta.objects.aggregate(Avg("total"))["total__avg"] or Decimal(0)

    context = {
        "ventas": ventas,
        "query": query,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "estado_filtro": estado_filtro,
        "cliente_id": cliente_id,
        "clientes": Usuario.objects.all(),
        "total_ventas": Venta.objects.count(),
        "monto_total": format_money(monto_total),
        "promedio_venta": format_money(promedio_venta),
        "clientes_unicos": Venta.objects.values("cliente").distinct().count(),
        "validaciones_pendientes": ValidacionVenta.objects.filter(estado__iexact="pendiente").count(),
        "validaciones_comprado": ValidacionVenta.objects.filter(estado__iexact="comprado").count(),
        "validaciones_rechazado": ValidacionVenta.objects.filter(estado__iexact="rechazado").count(),
    }
    return render(request, "ventas/dashboard/lista.html", context)


@admin_required_session
def venta_nueva(request):
    if request.method == "POST":
        cliente = get_object_or_404(Usuario, id=request.POST.get("cliente_id"))
        total = parse_money(request.POST.get("total"))
        venta = Venta.objects.create(cliente=cliente, total=total)
        return redirect("ventas:venta_detalle", venta_id=venta.id)
    clientes = Usuario.objects.all()
    return render(request, "ventas/dashboard/nueva.html", {"clientes": clientes})


@admin_required_session
def venta_detalle(request, venta_id):
    venta = get_object_or_404(Venta.objects.select_related("cliente"), id=venta_id)
    return render(request, "ventas/dashboard/detalle.html", {"venta": venta})


@admin_required_session
def venta_validaciones(request, venta_id):
    venta = get_object_or_404(Venta, id=venta_id)
    if request.method == "POST":
        validacion = venta.validaciones.order_by("-fecha_validacion").first()

        if validacion:
            validacion.metodo_pago = request.POST.get("metodo_pago", "")
            validacion.referencia_pago = request.POST.get("referencia_pago", "")
            validacion.monto = parse_money(request.POST.get("monto"))
            nuevo_estado = request.POST.get("estado", "pendiente")
            validacion.estado = nuevo_estado
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
                cliente=venta.cliente,
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

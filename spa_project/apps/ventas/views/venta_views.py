from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.db import transaction

from apps.sesiones.decorators import admin_required_session
from apps.sesiones.models import Usuario
from apps.ventas.telegram_notifier import notificar_compra_pendiente
from apps.ventas.models import ValidacionVenta, Venta


from decimal import Decimal
from datetime import datetime, timedelta
from django.db.models import Sum, Count, Q, Avg

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.db import transaction

from apps.sesiones.decorators import admin_required_session
from apps.sesiones.models import Usuario
from apps.ventas.telegram_notifier import notificar_compra_pendiente
from apps.ventas.models import ValidacionVenta, Venta, DetalleVenta


@admin_required_session
def venta_lista(request):
    """Lista de ventas con filtros avanzados"""
    query = request.GET.get("q", "")
    fecha_inicio = request.GET.get("fecha_inicio", "")
    fecha_fin = request.GET.get("fecha_fin", "")
    estado_filtro = request.GET.get("estado", "")
    cliente_id = request.GET.get("cliente_id", "")
    
    # Filtros de fecha
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
    
    # Busqueda por cliente
    if query:
        ventas = ventas.filter(cliente__nombre__icontains=query)
    
    # Filtro de cliente
    if cliente_id:
        ventas = ventas.filter(cliente_id=cliente_id)
    
    # Filtro de estado (desde validaciones)
    if estado_filtro:
        venta_ids = ValidacionVenta.objects.filter(estado=estado_filtro).values_list("venta_id", flat=True)
        ventas = ventas.filter(id__in=venta_ids)
    
    # Aplicar filtro de fechas
    if filtro_fecha:
        ventas = ventas.filter(filtro_fecha)
    
    # Estadísticas
    total_ventas = Venta.objects.count()
    monto_total = Venta.objects.aggregate(Sum("total"))["total__sum"] or Decimal(0)
    promedio_venta = Venta.objects.aggregate(Avg("total"))["total__avg"] or Decimal(0)
    
    # Estados de validación
    validaciones_pendientes = ValidacionVenta.objects.filter(estado="pendiente").count()
    validaciones_comprado = ValidacionVenta.objects.filter(estado="comprado").count()
    validaciones_rechazado = ValidacionVenta.objects.filter(estado="rechazado").count()
    
    # Clientes únicos
    clientes_unicos = Venta.objects.values("cliente").distinct().count()
    
    # Obtener lista de clientes para filtro
    clientes = Usuario.objects.all()
    
    context = {
        "ventas": ventas,
        "query": query,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "estado_filtro": estado_filtro,
        "cliente_id": cliente_id,
        "clientes": clientes,
        "total_ventas": total_ventas,
        "monto_total": f"${float(monto_total):,.2f}",
        "promedio_venta": f"${float(promedio_venta):,.2f}",
        "clientes_unicos": clientes_unicos,
        "validaciones_pendientes": validaciones_pendientes,
        "validaciones_comprado": validaciones_comprado,
        "validaciones_rechazado": validaciones_rechazado,
    }
    return render(request, "ventas/lista.html", context)


@admin_required_session
def venta_nueva(request):
    if request.method == "POST":
        cliente = get_object_or_404(Usuario, id=request.POST.get("cliente_id"))
        total = Decimal(request.POST.get("total") or "0")
        venta = Venta.objects.create(cliente=cliente, total=total)
        return redirect("ventas:venta_detalle", venta_id=venta.id)
    clientes = Usuario.objects.all()
    return render(request, "ventas/nueva.html", {"clientes": clientes})


@admin_required_session
def venta_detalle(request, venta_id):
    venta = get_object_or_404(Venta.objects.select_related("cliente"), id=venta_id)
    return render(request, "ventas/detalle.html", {"venta": venta})


@admin_required_session
def venta_validaciones(request, venta_id):
    """Gestión de validaciones de venta con filtros"""
    venta = get_object_or_404(Venta, id=venta_id)
    if request.method == "POST":
        # Registra la validacion de pago y dispara aviso por Telegram si queda pendiente.
        validacion = ValidacionVenta.objects.create(
            venta=venta,
            cliente=venta.cliente,
            metodo_pago=request.POST.get("metodo_pago", ""),
            referencia_pago=request.POST.get("referencia_pago", ""),
            monto=request.POST.get("monto") or 0,
            estado=request.POST.get("estado", "pendiente"),
            validado_por=request.session.get("usuario_id"),
            observaciones=request.POST.get("observaciones", ""),
        )
        if validacion.estado == "pendiente":
            sent = notificar_compra_pendiente(venta=venta, validacion=validacion)
            if not sent:
                messages.warning(
                    request,
                    "La validacion quedo pendiente, pero fallo el envio a Telegram.",
                )
        messages.success(request, "Validación registrada correctamente")
        return redirect("ventas:venta_validaciones", venta_id=venta.id)
    
    validaciones = venta.validaciones.all()
    
    # Estadísticas de validaciones
    validaciones_pendientes = ValidacionVenta.objects.filter(estado="pendiente").count()
    validaciones_comprado = ValidacionVenta.objects.filter(estado="comprado").count()
    validaciones_rechazado = ValidacionVenta.objects.filter(estado="rechazado").count()
    
    context = {
        "venta": venta,
        "validaciones": validaciones,
        "validaciones_pendientes": validaciones_pendientes,
        "validaciones_comprado": validaciones_comprado,
        "validaciones_rechazado": validaciones_rechazado,
    }
    return render(request, "ventas/validaciones.html", context)


def confirmar_compra_telegram(request, validacion_id):
    # Endpoint invocado desde Telegram para confirmar la compra.
    token = request.GET.get("token", "")
    if token != getattr(settings, "TELEGRAM_CONFIRM_TOKEN", ""):
        return HttpResponseForbidden("Token invalido.")

    validacion = get_object_or_404(ValidacionVenta, id=validacion_id)
    if validacion.estado == "comprado":
        return HttpResponse("La compra ya esta confirmada.")

    detalles = validacion.venta.detalles.select_related("producto").all()
    for detalle in detalles:
        if detalle.producto.stock < detalle.cantidad:
            return HttpResponse(
                f"No se pudo confirmar: stock insuficiente para {detalle.producto.nombre}."
            )

    with transaction.atomic():
        # Descuenta stock de forma atomica para evitar inconsistencias.
        for detalle in detalles:
            producto = detalle.producto
            producto.stock -= detalle.cantidad
            producto.save(update_fields=["stock"])

    validacion.estado = "comprado"
    validacion.observaciones = "Confirmado "
    validacion.save(update_fields=["estado", "observaciones"])
    return HttpResponse("Compra confirmada correctamente.")


def rechazar_compra_telegram(request, validacion_id):
    # Endpoint invocado desde Telegram para rechazar la compra.
    token = request.GET.get("token", "")
    if token != getattr(settings, "TELEGRAM_CONFIRM_TOKEN", ""):
        return HttpResponseForbidden("Token invalido.")

    validacion = get_object_or_404(ValidacionVenta, id=validacion_id)
    validacion.estado = "rechazado"
    validacion.observaciones = "Rechazado "
    validacion.save(update_fields=["estado", "observaciones"])
    return HttpResponse("Compra rechazada correctamente.")

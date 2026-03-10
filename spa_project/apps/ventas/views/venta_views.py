from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.db import transaction

from apps.sesiones.decorators import admin_required_session
from apps.sesiones.models import Usuario
from apps.ventas.telegram_notifier import notify_pending_purchase
from apps.ventas.models import ValidacionVenta, Venta


@admin_required_session
def venta_lista(request):
    ventas = Venta.objects.select_related("cliente").order_by("-fecha")
    return render(request, "ventas/lista.html", {"ventas": ventas})


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
    venta = get_object_or_404(Venta, id=venta_id)
    if request.method == "POST":
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
            sent = notify_pending_purchase(venta=venta, validacion=validacion)
            if not sent:
                messages.warning(
                    request,
                    "La validacion quedo pendiente, pero fallo el envio a Telegram.",
                )
        return redirect("ventas:venta_validaciones", venta_id=venta.id)
    validaciones = venta.validaciones.all()
    return render(
        request,
        "ventas/validaciones.html",
        {"venta": venta, "validaciones": validaciones},
    )


def telegram_confirm_purchase(request, validacion_id):
    token = request.GET.get("token", "")
    if token != getattr(settings, "TELEGRAM_CONFIRM_TOKEN", ""):
        return HttpResponseForbidden("Token invalido.")

    validacion = get_object_or_404(ValidacionVenta, id=validacion_id)
    if validacion.estado == "comprado":
        return HttpResponse("La compra ya estaba confirmada.")

    detalles = validacion.venta.detalles.select_related("producto").all()
    for detalle in detalles:
        if detalle.producto.stock < detalle.cantidad:
            return HttpResponse(
                f"No se pudo confirmar: stock insuficiente para {detalle.producto.nombre}."
            )

    with transaction.atomic():
        for detalle in detalles:
            producto = detalle.producto
            producto.stock -= detalle.cantidad
            producto.save(update_fields=["stock"])

    validacion.estado = "comprado"
    validacion.observaciones = "Confirmado desde Telegram."
    validacion.save(update_fields=["estado", "observaciones"])
    return HttpResponse("Compra confirmada correctamente.")


def telegram_reject_purchase(request, validacion_id):
    token = request.GET.get("token", "")
    if token != getattr(settings, "TELEGRAM_CONFIRM_TOKEN", ""):
        return HttpResponseForbidden("Token invalido.")

    validacion = get_object_or_404(ValidacionVenta, id=validacion_id)
    validacion.estado = "rechazado"
    validacion.observaciones = "Rechazado desde Telegram."
    validacion.save(update_fields=["estado", "observaciones"])
    return HttpResponse("Compra rechazada correctamente.")

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect

from apps.sesiones.decorators import login_required_session
from apps.ventas.devoluciones import (
    aprobar_solicitud_devolucion,
    cantidad_disponible_para_devolucion,
    rechazar_solicitud_devolucion,
)
from apps.ventas.models import DetalleVenta, SolicitudDevolucionVenta
from apps.ventas.telegram_notifier import notificar_solicitud_devolucion


def _venta_confirmada(venta):
    validacion = venta.validaciones.order_by("-fecha_validacion", "-id").first()
    if not validacion:
        return False
    return (validacion.estado or "").strip().lower() == "comprado"


def _redirect_perfil_devoluciones():
    return redirect("sesiones:perfil")


@login_required_session
def solicitar_devolucion(request, detalle_id):
    if request.method != "POST":
        return redirect("sesiones:perfil")

    detalle = get_object_or_404(
        DetalleVenta.objects.select_related("venta__cliente", "producto"),
        id=detalle_id,
    )
    usuario_id = request.session.get("usuario_id")

    if detalle.venta.cliente_id != usuario_id:
        messages.error(request, "No puedes solicitar devoluciones sobre compras de otro cliente.")
        return _redirect_perfil_devoluciones()

    if not _venta_confirmada(detalle.venta):
        messages.error(request, "Solo puedes devolver productos de compras confirmadas.")
        return _redirect_perfil_devoluciones()

    try:
        cantidad = int(request.POST.get("cantidad") or 0)
    except (TypeError, ValueError):
        cantidad = 0

    motivo = (request.POST.get("motivo") or "").strip()
    if cantidad <= 0:
        messages.error(request, "La cantidad a devolver debe ser mayor a cero.")
        return _redirect_perfil_devoluciones()

    if not (15 <= len(motivo) <= 200):
        messages.error(request, "El motivo de la devolucion debe tener entre 15 y 200 caracteres.")
        return _redirect_perfil_devoluciones()

    cantidad_disponible = cantidad_disponible_para_devolucion(detalle)
    if cantidad > cantidad_disponible:
        messages.error(
            request,
            f"Solo puedes solicitar {cantidad_disponible} unidades para este producto.",
        )
        return _redirect_perfil_devoluciones()

    solicitud = SolicitudDevolucionVenta.objects.create(
        detalle_venta=detalle,
        cliente_id=usuario_id,
        cantidad=cantidad,
        motivo=motivo,
    )

    sent = notificar_solicitud_devolucion(solicitud)
    if sent:
        messages.success(
            request,
            "Tu solicitud de devolucion fue enviada al administrador.",
        )
    else:
        messages.warning(
            request,
            "La solicitud quedo registrada, pero no se pudo enviar a Telegram.",
        )

    return _redirect_perfil_devoluciones()


def aprobar_devolucion_telegram(request, solicitud_id):
    token = request.GET.get("token", "")
    if token != getattr(settings, "TELEGRAM_CONFIRM_TOKEN", ""):
        return HttpResponseForbidden("Token invalido.")

    solicitud = get_object_or_404(
        SolicitudDevolucionVenta.objects.select_related(
            "cliente",
            "detalle_venta__venta",
            "detalle_venta__producto",
        ),
        id=solicitud_id,
    )

    if solicitud.estado == SolicitudDevolucionVenta.ESTADO_APROBADA:
        return HttpResponse("La devolucion ya fue aprobada.")
    if solicitud.estado == SolicitudDevolucionVenta.ESTADO_RECHAZADA:
        return HttpResponse("La devolucion ya fue rechazada previamente.")

    aprobar_solicitud_devolucion(solicitud)
    return HttpResponse("Devolucion aprobada correctamente.")


def rechazar_devolucion_telegram(request, solicitud_id):
    token = request.GET.get("token", "")
    if token != getattr(settings, "TELEGRAM_CONFIRM_TOKEN", ""):
        return HttpResponseForbidden("Token invalido.")

    solicitud = get_object_or_404(
        SolicitudDevolucionVenta.objects.select_related(
            "cliente",
            "detalle_venta__venta",
            "detalle_venta__producto",
        ),
        id=solicitud_id,
    )

    if solicitud.estado == SolicitudDevolucionVenta.ESTADO_RECHAZADA:
        return HttpResponse("La devolucion ya fue rechazada.")
    if solicitud.estado == SolicitudDevolucionVenta.ESTADO_APROBADA:
        return HttpResponse("La devolucion ya fue aprobada previamente.")

    rechazar_solicitud_devolucion(solicitud)
    return HttpResponse("Devolucion rechazada correctamente.")

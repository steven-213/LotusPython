from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.inventario.services import registrar_ingreso
from apps.ventas.models import SolicitudDevolucionVenta


def cantidad_solicitada_para_detalle(detalle_venta, *, excluir_solicitud_id=None):
    solicitudes = detalle_venta.solicitudes_devolucion.exclude(
        estado=SolicitudDevolucionVenta.ESTADO_RECHAZADA
    )
    if excluir_solicitud_id is not None:
        solicitudes = solicitudes.exclude(id=excluir_solicitud_id)
    return solicitudes.aggregate(total=Sum("cantidad"))["total"] or 0


def cantidad_disponible_para_devolucion(detalle_venta, *, excluir_solicitud_id=None):
    cantidad_solicitada = cantidad_solicitada_para_detalle(
        detalle_venta,
        excluir_solicitud_id=excluir_solicitud_id,
    )
    return max(detalle_venta.cantidad - cantidad_solicitada, 0)


@transaction.atomic
def aprobar_solicitud_devolucion(
    solicitud,
    *,
    comentario_admin="Devolucion aprobada por el administrador.",
):
    if solicitud.estado != SolicitudDevolucionVenta.ESTADO_PENDIENTE:
        return False

    producto = solicitud.detalle_venta.producto
    registrar_ingreso(
        producto,
        solicitud.cantidad,
        lote=f"DEV-VENTA-{solicitud.id}",
    )

    solicitud.estado = SolicitudDevolucionVenta.ESTADO_APROBADA
    solicitud.comentario_admin = comentario_admin
    solicitud.fecha_respuesta = timezone.now()
    solicitud.save(update_fields=["estado", "comentario_admin", "fecha_respuesta"])
    return True


@transaction.atomic
def rechazar_solicitud_devolucion(
    solicitud,
    *,
    comentario_admin="Devolucion rechazada por el administrador.",
):
    if solicitud.estado != SolicitudDevolucionVenta.ESTADO_PENDIENTE:
        return False

    solicitud.estado = SolicitudDevolucionVenta.ESTADO_RECHAZADA
    solicitud.comentario_admin = comentario_admin
    solicitud.fecha_respuesta = timezone.now()
    solicitud.save(update_fields=["estado", "comentario_admin", "fecha_respuesta"])
    return True

from decimal import Decimal

from django.shortcuts import render
from django.utils import timezone

from apps.citas.models import Reserva
from apps.membresias.services import obtener_membresia_activa
from apps.sesiones.decorators import login_required_session
from apps.sesiones.models import Usuario
from apps.ventas.models import SolicitudDevolucionVenta, ValidacionVenta


def _resumir_productos(nombres):
    nombres = [nombre for nombre in nombres if nombre]
    if not nombres:
        return "Sin productos"
    if len(nombres) == 1:
        return nombres[0]
    if len(nombres) == 2:
        return f"{nombres[0]} y {nombres[1]}"
    return f"{nombres[0]}, {nombres[1]} y {len(nombres) - 2} mas"


def _resolver_estado_devolucion(detalle, solicitudes):
    pendientes = [s for s in solicitudes if s.estado == SolicitudDevolucionVenta.ESTADO_PENDIENTE]
    aprobadas = [s for s in solicitudes if s.estado == SolicitudDevolucionVenta.ESTADO_APROBADA]
    rechazadas = [s for s in solicitudes if s.estado == SolicitudDevolucionVenta.ESTADO_RECHAZADA]

    cantidad_aprobada = sum(s.cantidad for s in aprobadas)

    if pendientes:
        return {
            "slug": "pendiente",
            "label": "En espera",
            "detalle": f"{len(pendientes)} solicitud pendiente",
        }

    if cantidad_aprobada >= detalle.cantidad and cantidad_aprobada > 0:
        return {
            "slug": "devuelto",
            "label": "Devuelto",
            "detalle": "Producto devuelto por completo",
        }

    if cantidad_aprobada > 0:
        return {
            "slug": "devuelto_parcial",
            "label": "Devuelto parcial",
            "detalle": f"{cantidad_aprobada} unidad(es) aprobadas",
        }

    if rechazadas:
        return {
            "slug": "rechazado",
            "label": "Rechazada",
            "detalle": f"{len(rechazadas)} solicitud rechazada",
        }

    return {
        "slug": "sin_solicitud",
        "label": "Sin devolucion",
        "detalle": "Aun no hay solicitudes",
    }


def _resolver_estado_compra(validacion):
    estado = (validacion.estado or "").strip().lower()
    if estado == "comprado":
        return {"slug": "comprado", "label": "Confirmada"}
    if estado == "pendiente":
        return {"slug": "pendiente", "label": "Pendiente"}
    if estado in {"rechazado", "rechazada"}:
        return {"slug": "rechazada", "label": "Rechazada"}
    return {"slug": estado or "sin_estado", "label": (validacion.estado or "Sin estado").capitalize()}


def _resolver_estado_devolucion_venta(venta, solicitudes):
    solicitudes = sorted(
        solicitudes,
        key=lambda solicitud: (solicitud.fecha_solicitud, solicitud.id),
        reverse=True,
    )
    if not solicitudes:
        return {
            "slug": "sin_solicitud",
            "label": "Sin devolucion",
            "detalle": "No hay solicitudes registradas",
            "identificador": "",
        }

    pendientes = [s for s in solicitudes if s.estado == SolicitudDevolucionVenta.ESTADO_PENDIENTE]
    aprobadas = [s for s in solicitudes if s.estado == SolicitudDevolucionVenta.ESTADO_APROBADA]
    rechazadas = [s for s in solicitudes if s.estado == SolicitudDevolucionVenta.ESTADO_RECHAZADA]

    productos_devueltos = []
    for solicitud in solicitudes:
        nombre_producto = solicitud.detalle_venta.producto.nombre
        if nombre_producto not in productos_devueltos:
            productos_devueltos.append(nombre_producto)

    productos_resumen = _resumir_productos(productos_devueltos)
    cantidad_total_venta = sum(detalle.cantidad for detalle in venta.detalles.all())
    cantidad_aprobada = sum(s.cantidad for s in aprobadas)

    if pendientes:
        ultima = pendientes[0]
        return {
            "slug": "pendiente",
            "label": "En espera",
            "detalle": f"Producto: {productos_resumen}",
            "identificador": f"Solicitud #{ultima.id}",
        }

    if cantidad_aprobada >= cantidad_total_venta and cantidad_aprobada > 0:
        ultima = aprobadas[0]
        return {
            "slug": "devuelto",
            "label": "Devuelta total",
            "detalle": f"Producto: {productos_resumen}",
            "identificador": f"Solicitud #{ultima.id}",
        }

    if aprobadas:
        ultima = aprobadas[0]
        return {
            "slug": "devuelto_parcial",
            "label": "Devuelta parcial",
            "detalle": f"Producto: {productos_resumen}",
            "identificador": f"Solicitud #{ultima.id}",
        }

    ultima = rechazadas[0]
    return {
        "slug": "rechazada",
        "label": "Rechazada",
        "detalle": f"Producto: {productos_resumen}",
        "identificador": f"Solicitud #{ultima.id}",
    }


@login_required_session
def perfil(request):
    usuario_id = request.session.get("usuario_id")
    usuario = Usuario.objects.filter(id=usuario_id).first()
    membresia_actual = obtener_membresia_activa(usuario) if usuario else None
    membresias_historial = (
        list(usuario.membresias.select_related("plan").all()[:3])
        if usuario
        else []
    )

    validaciones = list(
        ValidacionVenta.objects.select_related("venta")
        .prefetch_related("venta__detalles__producto")
        .filter(cliente_id=usuario_id)
        .order_by("-fecha_validacion")
    )
    devoluciones = list(
        SolicitudDevolucionVenta.objects.select_related(
            "detalle_venta__venta",
            "detalle_venta__producto",
        )
        .filter(cliente_id=usuario_id)
        .order_by("-fecha_solicitud")
    )

    compras_pendientes = [v for v in validaciones if (v.estado or "").strip().lower() == "pendiente"]
    compras_compradas = [v for v in validaciones if (v.estado or "").strip().lower() == "comprado"]
    compras_rechazadas = [
        v
        for v in validaciones
        if (v.estado or "").strip().lower() in {"rechazado", "rechazada"}
    ]

    ahora = timezone.now()
    reservas = list(
        Reserva.objects.select_related("servicio")
        .filter(cliente_id=usuario_id)
        .order_by("-fecha_inicio")
    )

    agendas_proximas = []
    agendas_historial = []

    for reserva in reservas:
        estado = (reserva.estado or "").strip().lower()
        if reserva.fecha_inicio >= ahora and estado not in {"cancelada", "finalizada", "no_asistio"}:
            agendas_proximas.append(reserva)
        else:
            agendas_historial.append(reserva)

    agendas_proximas.sort(key=lambda r: r.fecha_inicio)

    devoluciones_por_detalle = {}
    for devolucion in devoluciones:
        devoluciones_por_detalle.setdefault(devolucion.detalle_venta_id, []).append(devolucion)

    productos_map = {}
    for compra in compras_compradas:
        for detalle in compra.venta.detalles.all():
            producto_id = detalle.producto_id
            producto_resumen = productos_map.get(producto_id)
            if producto_resumen is None:
                producto_resumen = {
                    "producto": detalle.producto,
                    "cantidad_total": 0,
                    "ordenes_ids": set(),
                    "total_gastado": Decimal("0"),
                    "ultima_compra": compra.fecha_validacion,
                }
                productos_map[producto_id] = producto_resumen

            producto_resumen["cantidad_total"] += detalle.cantidad
            producto_resumen["ordenes_ids"].add(compra.venta_id)
            producto_resumen["total_gastado"] += detalle.precio_unitario * detalle.cantidad
            if compra.fecha_validacion > producto_resumen["ultima_compra"]:
                producto_resumen["ultima_compra"] = compra.fecha_validacion

    productos_comprados = []
    for compra in compras_compradas:
        for detalle in compra.venta.detalles.all():
            solicitudes_detalle = devoluciones_por_detalle.get(detalle.id, [])
            cantidad_reservada = sum(
                solicitud.cantidad
                for solicitud in solicitudes_detalle
                if solicitud.estado != SolicitudDevolucionVenta.ESTADO_RECHAZADA
            )
            productos_comprados.append(
                {
                    "detalle": detalle,
                    "producto": detalle.producto,
                    "venta_id": compra.venta.id,
                    "estado_compra": "Confirmada",
                    "cantidad_comprada": detalle.cantidad,
                    "fecha_compra": compra.fecha_validacion,
                    "total_gastado": detalle.precio_unitario * detalle.cantidad,
                    "cantidad_disponible": max(detalle.cantidad - cantidad_reservada, 0),
                    "solicitudes": solicitudes_detalle,
                    "estado_devolucion": _resolver_estado_devolucion(
                        detalle,
                        solicitudes_detalle,
                    ),
                }
            )

    productos_comprados.sort(
        key=lambda item: (item["fecha_compra"], item["detalle"].id),
        reverse=True,
    )

    devoluciones_por_venta = {}
    for devolucion in devoluciones:
        devoluciones_por_venta.setdefault(devolucion.detalle_venta.venta_id, []).append(devolucion)

    validaciones_recientes = []
    for validacion in validaciones[:8]:
        productos_venta = [
            detalle.producto.nombre
            for detalle in validacion.venta.detalles.all()
        ]
        validaciones_recientes.append(
            {
                "validacion": validacion,
                "estado_compra": _resolver_estado_compra(validacion),
                "estado_devolucion": _resolver_estado_devolucion_venta(
                    validacion.venta,
                    devoluciones_por_venta.get(validacion.venta_id, []),
                ),
                "productos_resumen": _resumir_productos(productos_venta),
            }
        )

    items_comprados_total = sum(data["cantidad_total"] for data in productos_map.values())
    proxima_reserva = agendas_proximas[0] if agendas_proximas else None

    return render(
        request,
        "sesiones/public/perfil.html",
        {
            "usuario": usuario,
            "compras_pendientes": compras_pendientes,
            "compras_compradas": compras_compradas,
            "compras_rechazadas": compras_rechazadas,
            "agendas_proximas": agendas_proximas,
            "agendas_historial": agendas_historial,
            "membresia_actual": membresia_actual,
            "membresias_historial": membresias_historial,
            "productos_comprados": productos_comprados,
            "validaciones_recientes": validaciones_recientes,
            "proxima_reserva": proxima_reserva,
            "total_agendas": len(reservas),
            "total_productos_comprados": len(productos_map),
            "total_items_comprados": items_comprados_total,
        },
    )

from decimal import Decimal

from django.shortcuts import render
from django.utils import timezone

from apps.citas.models import Reserva
from apps.sesiones.decorators import login_required_session
from apps.sesiones.models import Usuario
from apps.ventas.models import ValidacionVenta


@login_required_session
def perfil(request):
    usuario_id = request.session.get("usuario_id")
    usuario = Usuario.objects.filter(id=usuario_id).first()

    validaciones = list(
        ValidacionVenta.objects.select_related("venta")
        .prefetch_related("venta__detalles__producto")
        .filter(cliente_id=usuario_id)
        .order_by("-fecha_validacion")
    )

    compras_pendientes = [v for v in validaciones if (v.estado or "").strip().lower() == "pendiente"]
    compras_compradas = [v for v in validaciones if (v.estado or "").strip().lower() == "comprado"]
    compras_rechazadas = [v for v in validaciones if (v.estado or "").strip().lower() == "rechazado"]

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

    productos_comprados = sorted(
        [
            {
                "producto": data["producto"],
                "cantidad_total": data["cantidad_total"],
                "ordenes": len(data["ordenes_ids"]),
                "total_gastado": data["total_gastado"],
                "ultima_compra": data["ultima_compra"],
            }
            for data in productos_map.values()
        ],
        key=lambda item: (item["ultima_compra"], item["cantidad_total"]),
        reverse=True,
    )

    items_comprados_total = sum(item["cantidad_total"] for item in productos_comprados)
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
            "productos_comprados": productos_comprados,
            "validaciones_recientes": validaciones[:8],
            "proxima_reserva": proxima_reserva,
            "total_agendas": len(reservas),
            "total_productos_comprados": len(productos_comprados),
            "total_items_comprados": items_comprados_total,
        },
    )

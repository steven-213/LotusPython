from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.inventario.services import descontar_stock, obtener_stock_disponible
from apps.ventas.models import DetalleVenta, ValidacionVenta, Venta


def registrar_venta_desde_reserva(
    *,
    reserva,
    items,
    metodo_pago="",
    referencia_pago="",
    validado_por=None,
):
    if not items:
        return None, Decimal("0")

    productos = []
    for item in items:
        producto = item["producto"]
        cantidad = int(item["cantidad"])
        if cantidad <= 0:
            raise ValidationError(f"La cantidad para {producto.nombre} debe ser mayor a cero.")
        stock_disponible = obtener_stock_disponible(producto)
        if stock_disponible < cantidad:
            raise ValidationError(
                f"No hay stock suficiente para {producto.nombre}. Disponible: {stock_disponible}."
            )
        productos.append((producto, cantidad))

    cliente = reserva.cliente

    with transaction.atomic():
        venta, creada = Venta.objects.select_for_update().get_or_create(
            reserva=reserva,
            defaults={
                "cliente": cliente,
                "subtotal_servicios": reserva.servicio.precio,
                "total": Decimal("0"),
            },
        )

        if not creada:
            venta.cliente = cliente
            if not venta.subtotal_servicios:
                venta.subtotal_servicios = reserva.servicio.precio

        total_productos_agregados = Decimal("0")
        for producto, cantidad in productos:
            try:
                descontar_stock(producto, cantidad)
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc
            detalle = venta.detalles.select_related("producto").filter(producto=producto).first()
            precio_unitario = getattr(producto, "precio_facturable", None) or producto.precio_venta
            if detalle:
                detalle.cantidad += cantidad
                detalle.precio_unitario = precio_unitario
                detalle.save(update_fields=["cantidad", "precio_unitario"])
            else:
                DetalleVenta.objects.create(
                    venta=venta,
                    producto=producto,
                    cantidad=cantidad,
                    precio_unitario=precio_unitario,
                )
            total_productos_agregados += precio_unitario * cantidad

        total_productos = sum(
            (detalle.cantidad * detalle.precio_unitario for detalle in venta.detalles.all()),
            Decimal("0"),
        )
        venta.total = total_productos
        venta.save(update_fields=["cliente", "subtotal_servicios", "total"])

        validacion = venta.validaciones.order_by("-fecha_validacion", "-id").first()
        if validacion:
            validacion.cliente = cliente
            validacion.metodo_pago = metodo_pago
            validacion.referencia_pago = referencia_pago
            validacion.monto = total_productos
            validacion.estado = "comprado"
            validacion.validado_por = validado_por
            validacion.observaciones = f"Venta asociada a la cita #{reserva.id}."
            validacion.save()
        else:
            ValidacionVenta.objects.create(
                venta=venta,
                cliente=cliente,
                metodo_pago=metodo_pago,
                referencia_pago=referencia_pago,
                monto=total_productos,
                estado="comprado",
                validado_por=validado_por,
                observaciones=f"Venta asociada a la cita #{reserva.id}.",
            )

    return venta, total_productos_agregados

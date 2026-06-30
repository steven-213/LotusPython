from django.db.models import IntegerField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.inventario.models import Inventario, Producto


DEFAULT_LOT_PREFIX = "LOTE"


def generar_lote_default(producto_id, *, prefix=DEFAULT_LOT_PREFIX):
    timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
    return f"{prefix}-{producto_id}-{timestamp}"


def anotar_stock_disponible(queryset):
    stock_disponible_subquery = Subquery(
        Inventario.objects.filter(producto=OuterRef("pk"))
        .values("producto")
        .annotate(total_stock=Sum("stock"))
        .values("total_stock")[:1],
        output_field=IntegerField(),
    )
    return queryset.annotate(
        stock_disponible=Coalesce(stock_disponible_subquery, Value(0), output_field=IntegerField())
    )


def queryset_productos_basico(*, activo=True):
    queryset = Producto.objects
    if activo is not None:
        queryset = queryset.filter(activo=activo)
    return queryset.only(
        "id",
        "nombre",
        "descripcion",
        "imagen",
        "precio_compra",
        "impuesto",
        "precio_venta",
        "margen_ganancia",
        "activo",
        "created_at",
        "updated_at",
        "proveedor_id",
    )


def obtener_stock_disponible(producto):
    lotes = list(
        Inventario.objects.filter(producto=producto).values_list("stock", flat=True)
    )
    if lotes:
        return sum(max(stock, 0) for stock in lotes)
    return 0


def sincronizar_stock_producto(producto):
    total_lotes = (
        Inventario.objects.filter(producto=producto).aggregate(total=Sum("stock"))["total"]
    )
    if total_lotes is None:
        return 0

    total_lotes = max(int(total_lotes), 0)
    return total_lotes


def registrar_ingreso(producto, cantidad, *, lote=None, fecha_ingreso=None):
    cantidad = int(cantidad or 0)
    if cantidad <= 0:
        return None

    lote = (lote or "").strip() or generar_lote_default(producto.id)
    defaults = {
        "stock": 0,
        "precio_venta": producto.precio_venta,
        "fecha_ingreso": fecha_ingreso or timezone.now(),
    }
    inventario, created = Inventario.objects.get_or_create(
        producto=producto,
        lote=lote,
        defaults=defaults,
    )

    inventario.stock += cantidad
    if created and fecha_ingreso is not None:
        inventario.fecha_ingreso = fecha_ingreso
    inventario.precio_venta = producto.precio_venta
    inventario.save(update_fields=["stock", "precio_venta", "fecha_ingreso"])

    sincronizar_stock_producto(producto)
    return inventario


def descontar_stock(producto, cantidad, *, lote=None):
    cantidad = int(cantidad or 0)
    if cantidad <= 0:
        return []

    lotes_qs = Inventario.objects.select_for_update().filter(producto=producto)
    if lote:
        lotes_qs = lotes_qs.filter(lote=lote)

    lotes = list(lotes_qs.order_by("fecha_ingreso", "id"))
    if lotes:
        disponible = sum(max(registro.stock, 0) for registro in lotes)
        if disponible < cantidad:
            raise ValueError("Stock insuficiente en inventario.")

        restante = cantidad
        consumos = []
        for registro in lotes:
            if restante <= 0:
                break
            if registro.stock <= 0:
                continue

            tomado = min(registro.stock, restante)
            registro.stock -= tomado
            registro.save(update_fields=["stock"])
            consumos.append((registro.lote, tomado))
            restante -= tomado

        sincronizar_stock_producto(producto)
        return consumos

    raise ValueError("Stock insuficiente en inventario.")

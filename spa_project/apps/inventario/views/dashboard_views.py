from django.shortcuts import render
from django.db.models import Count, Sum, F, DecimalField, IntegerField,Q
from django.db.models.functions import Coalesce
from datetime import datetime, timedelta
from django.db.models import OuterRef, Subquery
from apps.inventario.models import (
    Producto, Proveedor, Compra, DevolucionCompra,Inventario, MovimientoInventario
)
from apps.inventario.services import anotar_stock_disponible
from apps.sesiones.decorators import admin_required_session


@admin_required_session
def inventario_dashboard(request):
    """Dashboard principal de inventario"""

    fecha_inicio = request.GET.get("fecha_inicio")
    fecha_fin = request.GET.get("fecha_fin")
    proveedor_id = request.GET.get("proveedor_id")

    filtro_fecha = Q()

    if fecha_inicio:
        try:
            filtro_fecha &= Q(fecha__gte=datetime.strptime(fecha_inicio, "%Y-%m-%d"))
        except ValueError:
            fecha_inicio = None

    if fecha_fin:
        try:
            filtro_fecha &= Q(fecha__lte=datetime.strptime(fecha_fin, "%Y-%m-%d") + timedelta(days=1))
        except ValueError:
            fecha_fin = None

    total_productos = Producto.objects.filter(activo=True).count()
    total_proveedores = Proveedor.objects.filter(activo=True).count()
    total_compras = Compra.objects.count()
    total_devoluciones = DevolucionCompra.objects.count()

    compras_query = Compra.objects.select_related("proveedor")

    if filtro_fecha:
        compras_query = compras_query.filter(filtro_fecha)

    if proveedor_id:
        compras_query = compras_query.filter(proveedor_id=proveedor_id)

    compras_recientes = compras_query.order_by("-fecha")[:10]

    devoluciones_recientes = (
        DevolucionCompra.objects
        .select_related("compra", "producto")
        .order_by("-fecha")[:10]
    )

    devoluciones_pendientes = DevolucionCompra.objects.filter(estado="pendiente").count()
    devoluciones_aprobadas = DevolucionCompra.objects.filter(estado="aprobada").count()
    devoluciones_rechazadas = DevolucionCompra.objects.filter(estado="rechazada").count()

    productos_por_proveedor = (
        Producto.objects.filter(activo=True)
        .values("proveedor__nombre")
        .annotate(total=Count("id"))
        .order_by("-total")[:5]
    )

    ultimo_precio = Inventario.objects.filter(
        producto=OuterRef("producto__id")
    ).order_by("-fecha_ingreso").values("precio_venta")[:1]

    inventario = (
        Inventario.objects.filter(producto__activo=True)
        .values(
            "producto__id",
            "producto__nombre",
            "producto__proveedor__nombre",
        )
        .annotate(
            stock_total=Sum("stock"),
            precio_venta=Subquery(ultimo_precio)
        )
        .filter(stock_total__gt=0)
        .order_by("producto__nombre")
    )
    productos_disponibles = sum(1 for i in inventario if i["stock_total"] >= 10)
    productos_bajos = sum(1 for i in inventario if i["stock_total"] < 10)
    productos_sinstock = 0  
    inventario_critico = [item for item in inventario if item["stock_total"] < 10][:6]

    # --- NUEVA PARTE: calcular Top 5 Productos ---
    movimientos = MovimientoInventario.objects.filter(tipo="SALIDA", producto__activo=True)

    productos_stats = (
        movimientos.values("producto_id", "producto__nombre")
        .annotate(
            unidades_vendidas=Coalesce(Sum("cantidad"), 0, output_field=IntegerField()),
            ingreso_total=Coalesce(Sum(F("cantidad") * F("inventario__precio_venta")), 0, output_field=DecimalField())
        )
        .order_by("-unidades_vendidas")
    )
    mas_vendidos = productos_stats[:5]

    productos_disponibles = 0
    productos_bajos = 0
    productos_sinstock = 0

    for item in inventario:
        stock_total = item["stock_total"]

        if stock_total == 0:
            productos_sinstock += 1
        elif stock_total < 10:
            productos_bajos += 1
        else:
            productos_disponibles += 1

    inventario_critico = [
        item for item in inventario if item["stock_total"] < 10
    ][:6]

    context = {
        "total_productos": total_productos,
        "total_proveedores": total_proveedores,
        "total_compras": total_compras,
        "total_devoluciones": total_devoluciones,

        "compras_recientes": compras_recientes,

        "devoluciones_recientes": devoluciones_recientes,
        "devoluciones_pendientes": devoluciones_pendientes,
        "devoluciones_aprobadas": devoluciones_aprobadas,
        "devoluciones_rechazadas": devoluciones_rechazadas,

        "productos_disponibles": productos_disponibles,
        "productos_bajos": productos_bajos,
        "productos_sinstock": productos_sinstock,

        "productos_por_proveedor": productos_por_proveedor,

        "inventario": inventario,
        "inventario_critico": inventario_critico,

        "proveedores": Proveedor.objects.all(),
        "productos_por_proveedor": productos_por_proveedor,

        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "proveedor_id": proveedor_id,
    }

    return render(request, "inventario/dashboard/dashboard.html", context)

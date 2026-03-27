from django.shortcuts import render
from django.db.models import Count, Q
from datetime import datetime, timedelta

from apps.inventario.models import (
    Producto, Proveedor, Compra, DevolucionCompra
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

    productos_con_stock = anotar_stock_disponible(
        Producto.objects.filter(activo=True).select_related("proveedor").order_by("nombre")
    )

    inventario = [
        {
            "producto": producto,
            "stock": producto.stock_disponible,
            "precio": producto.precio_venta,
        }
        for producto in productos_con_stock
    ]

    productos_disponibles = 0
    productos_bajos = 0
    productos_sinstock = 0

    for item in inventario:
        stock = item["stock"]

        if stock == 0:
            productos_sinstock += 1
        elif stock < 10:
            productos_bajos += 1
        else:
            productos_disponibles += 1

    inventario_critico = [
        item for item in inventario if item["stock"] < 10
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
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "proveedor_id": proveedor_id,
    }

    return render(request, "inventario/dashboard/dashboard.html", context)

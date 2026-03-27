from datetime import datetime, timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.shortcuts import render

from apps.common.currency import format_money
from apps.inventario.models import Compra, DevolucionCompra, Producto, Proveedor
from apps.inventario.services import obtener_stock_disponible
from apps.sesiones.decorators import admin_required_session


@admin_required_session
def inventario_dashboard(request):
    fecha_inicio = request.GET.get("fecha_inicio")
    fecha_fin = request.GET.get("fecha_fin")
    proveedor_id = request.GET.get("proveedor_id")
    estado_compra = request.GET.get("estado_compra")

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

    productos_activos = list(Producto.objects.filter(activo=True).select_related("proveedor"))
    total_productos = len(productos_activos)
    total_proveedores = Proveedor.objects.filter(activo=True).count()
    total_compras = Compra.objects.count()
    total_devoluciones = DevolucionCompra.objects.count()

    total_stock = 0
    productos_bajo_stock = 0
    productos_sin_stock = 0
    valor_inventario = Decimal("0")
    valor_total_ventas_potencial = Decimal("0")
    productos_con_margen = []

    for producto in productos_activos:
        stock = obtener_stock_disponible(producto)
        total_stock += stock
        if stock == 0:
            productos_sin_stock += 1
        elif stock <= producto.stock_minimo:
            productos_bajo_stock += 1

        precio_compra = Decimal(str(producto.precio_compra or 0))
        precio_venta = Decimal(str(producto.precio_venta or 0))
        valor_inventario += precio_compra * Decimal(stock)
        valor_total_ventas_potencial += precio_venta * Decimal(stock)
        productos_con_margen.append(
            {
                "producto": producto,
                "margen": round(float(producto.margen_ganancia or 0), 2),
            }
        )

    productos_necesitan_reorden = productos_bajo_stock + productos_sin_stock
    margen_promedio = (
        sum(Decimal(str(item["margen"])) for item in productos_con_margen) / Decimal(total_productos)
        if total_productos
        else Decimal("0")
    )

    compras_query = Compra.objects.select_related("proveedor")
    if filtro_fecha:
        compras_query = compras_query.filter(filtro_fecha)
    if proveedor_id:
        compras_query = compras_query.filter(proveedor_id=proveedor_id)
    if estado_compra and estado_compra != "completada":
        compras_query = compras_query.none()

    compras_recientes = compras_query.order_by("-fecha")[:10]
    compras_completadas = Compra.objects.count()
    compras_pendientes = 0
    compras_canceladas = 0
    total_invertido = Compra.objects.aggregate(Sum("total"))["total__sum"] or Decimal(0)
    compras_completadas_monto = total_invertido

    devoluciones_recientes = DevolucionCompra.objects.select_related("compra", "producto").order_by("-fecha")[:10]
    devoluciones_pendientes = DevolucionCompra.objects.filter(estado="pendiente").count()
    devoluciones_aprobadas = DevolucionCompra.objects.filter(estado="aprobada").count()
    devoluciones_rechazadas = DevolucionCompra.objects.filter(estado="rechazada").count()

    productos_por_proveedor = (
        Producto.objects.values("proveedor__nombre").annotate(count=Count("id")).order_by("-count")[:5]
    )
    top_margenes = sorted(productos_con_margen, key=lambda x: x["margen"], reverse=True)[:5]

    context = {
        "total_productos": total_productos,
        "total_proveedores": total_proveedores,
        "total_compras": total_compras,
        "total_devoluciones": total_devoluciones,
        "total_stock": total_stock,
        "productos_bajo_stock": productos_bajo_stock,
        "productos_sin_stock": productos_sin_stock,
        "productos_necesitan_reorden": productos_necesitan_reorden,
        "valor_inventario": format_money(valor_inventario),
        "valor_total_ventas_potencial": format_money(valor_total_ventas_potencial),
        "margen_promedio": f"{float(margen_promedio):.2f}%",
        "top_margenes": top_margenes,
        "compras_recientes": compras_recientes,
        "compras_completadas": compras_completadas,
        "compras_pendientes": compras_pendientes,
        "compras_canceladas": compras_canceladas,
        "total_invertido": format_money(total_invertido),
        "compras_completadas_monto": format_money(compras_completadas_monto),
        "devoluciones_recientes": devoluciones_recientes,
        "devoluciones_pendientes": devoluciones_pendientes,
        "devoluciones_aprobadas": devoluciones_aprobadas,
        "devoluciones_rechazadas": devoluciones_rechazadas,
        "productos_por_proveedor": productos_por_proveedor,
        "proveedores": Proveedor.objects.all(),
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "proveedor_id": proveedor_id,
        "estado_compra": estado_compra,
    }
    return render(request, "inventario/dashboard/dashboard.html", context)

from django.shortcuts import render
from django.db.models import Count, Sum, F, DecimalField, IntegerField, Q
from django.db.models.functions import Coalesce
from datetime import datetime, timedelta
from django.db.models import OuterRef, Subquery
from apps.inventario.models import (
    Producto, Proveedor, Compra, DevolucionCompra, Inventario, MovimientoInventario
)
from apps.sesiones.decorators import admin_required_session


@admin_required_session
def inventario_dashboard(request):
    """Dashboard principal de inventario optimizado"""

    fecha_inicio = request.GET.get("fecha_inicio")
    fecha_fin = request.GET.get("fecha_fin")
    proveedor_id = request.GET.get("proveedor_id")

    filtro_fecha = Q()
    filtro_fecha_movimientos = Q()

    # Formateo correcto de rangos de fecha
    if fecha_inicio:
        try:
            inicio_dt = datetime.strptime(fecha_inicio, "%Y-%m-%d")
            filtro_fecha &= Q(fecha__gte=inicio_dt)
            filtro_fecha_movimientos &= Q(fecha__gte=inicio_dt)
        except ValueError:
            fecha_inicio = None

    if fecha_fin:
        try:
            fin_dt = datetime.strptime(fecha_fin, "%Y-%m-%d") + timedelta(days=1)
            filtro_fecha &= Q(fecha__lte=fin_dt)
            filtro_fecha_movimientos &= Q(fecha__lte=fin_dt)
        except ValueError:
            fecha_fin = None

    # Contadores Globales Base
    total_productos = Producto.objects.filter(activo=True).count()
    total_proveedores = Proveedor.objects.filter(activo=True).count()
    
    # Construcción de Queries dependientes de filtros de cabecera
    compras_query = Compra.objects.select_related("proveedor")
    devoluciones_query = DevolucionCompra.objects.select_related("compra", "producto")
    movimientos_query = MovimientoInventario.objects.filter(tipo="SALIDA", producto__activo=True)

    if filtro_fecha:
        compras_query = compras_query.filter(filtro_fecha)
        devoluciones_query = devoluciones_query.filter(filtro_fecha)
        movimientos_query = movimientos_query.filter(filtro_fecha_movimientos)

    if proveedor_id:
        compras_query = compras_query.filter(proveedor_id=proveedor_id)
        devoluciones_query = devoluciones_query.filter(compra__proveedor_id=proveedor_id)
        movimientos_query = movimientos_query.filter(producto__proveedor_id=proveedor_id)

    # Totales calculados post-filtros
    total_compras = compras_query.count()
    total_devoluciones = devoluciones_query.count()

    compras_recientes = compras_query.order_by("-fecha")[:10]
    devoluciones_recientes = devoluciones_query.order_by("-fecha")[:10]

    devoluciones_pendientes = devoluciones_query.filter(estado="pendiente").count()
    devoluciones_aprobadas = devoluciones_query.filter(estado="aprobada").count()
    devoluciones_rechazadas = devoluciones_query.filter(estado="rechazada").count()

    # Gráfico / Métrica de Proveedores
    productos_por_proveedor = (
        Producto.objects.filter(activo=True)
        .values("proveedor__nombre")
        .annotate(total=Count("id"))
        .order_by("-total")[:5]
    )

    # Subquery optimizada para obtener el último precio de venta asignado a un lote
    ultimo_precio = (
        Inventario.objects.filter(producto=OuterRef("id"))
        .order_by("-fecha_ingreso")
        .values("precio_venta")[:1]
    )

    # REFACTOR: Obtenemos TODOS los productos activos para poder calcular los "Sin Stock" de forma real
    inventario_base = (
        Producto.objects.filter(activo=True)
        .values("id", "nombre", "proveedor__nombre")
        .annotate(
            stock_total=Coalesce(Sum("inventario__stock"), 0, output_field=IntegerField()),
            precio_venta=Subquery(ultimo_precio)
        )
        .order_by("nombre")
    )

    # Clasificación de alertas de Stock en una sola pasada (O(N))
    productos_disponibles = 0
    productos_bajos = 0
    productos_sinstock = 0
    inventario_critico = []

    for item in inventario_base:
        stock = item["stock_total"]
        if stock == 0:
            productos_sinstock += 1
            if len(inventario_critico) < 6:
                inventario_critico.append(item)
        elif stock < 10:
            productos_bajos += 1
            if len(inventario_critico) < 6:
                inventario_critico.append(item)
        else:
            productos_disponibles += 1

    # --- Top 5 Productos Más Vendidos ---
    mas_vendidos = (
        movimientos_query.values("producto_id", "producto__nombre")
        .annotate(
            unidades_vendidas=Coalesce(Sum("cantidad"), 0, output_field=IntegerField()),
            ingreso_total=Coalesce(Sum(F("cantidad") * F("inventario__precio_venta")), 0, output_field=DecimalField())
        )
        .order_by("-unidades_vendidas")[:5]
    )

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

        "inventario": [i for i in inventario_base if i["stock_total"] > 0],  # Lista limpia para la tabla general
        "inventario_critico": inventario_critico,
        "mas_vendidos": mas_vendidos,  # ¡Agregado al contexto!

        "proveedores": Proveedor.objects.all(),
        "productos_por_proveedor": productos_por_proveedor,

        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "proveedor_id": proveedor_id,
    }

    return render(request, "inventario/dashboard/dashboard.html", context)

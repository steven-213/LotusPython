from django.shortcuts import render
from django.db.models import Sum, Count, Q, F, Avg, DecimalField
from django.db.models.functions import Cast
from decimal import Decimal
from datetime import datetime, timedelta

from apps.inventario.models import Producto, Proveedor, Compra, DevolucionCompra
from apps.sesiones.decorators import admin_required_session


@admin_required_session
def inventario_dashboard(request):
    """Dashboard principal de inventario con estadísticas y filtros"""
    
    # ==================== FILTROS ====================
    fecha_inicio = request.GET.get("fecha_inicio")
    fecha_fin = request.GET.get("fecha_fin")
    proveedor_id = request.GET.get("proveedor_id")
    estado_compra = request.GET.get("estado_compra")
    
    # Convertir fechas si existen
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
    
    # ==================== ESTADÍSTICAS GENERALES ====================
    total_productos = Producto.objects.filter(activo=True).count()
    total_proveedores = Proveedor.objects.filter(activo=True).count()
    total_compras = Compra.objects.count()
    total_devoluciones = DevolucionCompra.objects.count()
    
    # ==================== STOCK ====================
    total_stock = Producto.objects.aggregate(Sum("stock"))["stock__sum"] or 0
    productos_bajo_stock = Producto.objects.filter(stock__lte=F("stock_minimo"), activo=True).count()
    productos_sin_stock = Producto.objects.filter(stock=0, activo=True).count()
    productos_necesitan_reorden = productos_bajo_stock  # Sin stock o bajo stock es lo mismo
    
    # ==================== VALOR INVENTARIO Y MÁRGENES ====================
    valor_inventario = Decimal(0)
    valor_total_ventas_potencial = Decimal(0)
    productos_con_margen = []
    margen_promedio = Decimal(0)
    
    productos_activos = Producto.objects.filter(activo=True).select_related("proveedor")
    total_productos_activos = productos_activos.count()
    
    for producto in productos_activos:
        precio_compra = Decimal(str(producto.precio_compra))
        precio_venta = Decimal(str(producto.precio_venta))
        stock = Decimal(str(producto.stock))
        
        valor_inventario += precio_compra * stock
        valor_total_ventas_potencial += precio_venta * stock
        
        if precio_compra > 0:
            margen = ((precio_venta - precio_compra) / precio_compra) * 100
            margen_promedio += margen
            productos_con_margen.append({
                "producto": producto,
                "margen": round(float(margen), 2)
            })
    
    margen_promedio = margen_promedio / total_productos_activos if total_productos_activos > 0 else Decimal(0)
    
    # ==================== COMPRAS ====================
    compras_query = Compra.objects.select_related("proveedor")
    
    # Aplicar filtros de compras
    if filtro_fecha:
        compras_query = compras_query.filter(filtro_fecha)
    if proveedor_id:
        compras_query = compras_query.filter(proveedor_id=proveedor_id)
    if estado_compra:
        compras_query = compras_query.filter(estado=estado_compra)
    
    compras_recientes = compras_query.order_by("-fecha")[:10]
    
    # Estadísticas de compras
    compras_completadas = Compra.objects.filter(estado="completada").count()
    compras_pendientes = Compra.objects.filter(estado="pendiente").count()
    compras_canceladas = Compra.objects.filter(estado="cancelada").count()
    
    total_invertido = Compra.objects.aggregate(Sum("total"))["total__sum"] or Decimal(0)
    compras_completadas_monto = Compra.objects.filter(estado="completada").aggregate(Sum("total"))["total__sum"] or Decimal(0)
    
    # ==================== DEVOLUCIONES ====================
    devoluciones_recientes = DevolucionCompra.objects.select_related(
        "compra", "producto"
    ).order_by("-fecha")[:10]
    
    devoluciones_pendientes = DevolucionCompra.objects.filter(estado="pendiente").count()
    devoluciones_aprobadas = DevolucionCompra.objects.filter(estado="aprobada").count()
    devoluciones_rechazadas = DevolucionCompra.objects.filter(estado="rechazada").count()
    
    # ==================== PRODUCTOS POR PROVEEDOR ====================
    productos_por_proveedor = (
        Producto.objects.values("proveedor__nombre")
        .annotate(count=Count("id"))
        .order_by("-count")[:5]
    )
    
    # ==================== TOP PRODUCTOS POR MARGEN ====================
    top_margenes = sorted(
        productos_con_margen,
        key=lambda x: x["margen"],
        reverse=True
    )[:5]
    
    # ==================== CONTEXTO ====================
    context = {
        # Estadísticas generales
        "total_productos": total_productos,
        "total_proveedores": total_proveedores,
        "total_compras": total_compras,
        "total_devoluciones": total_devoluciones,
        
        # Stock
        "total_stock": total_stock,
        "productos_bajo_stock": productos_bajo_stock,
        "productos_sin_stock": productos_sin_stock,
        "productos_necesitan_reorden": productos_necesitan_reorden,
        
        # Valor inventario
        "valor_inventario": f"${float(valor_inventario):,.2f}",
        "valor_total_ventas_potencial": f"${float(valor_total_ventas_potencial):,.2f}",
        
        # Márgenes
        "margen_promedio": f"{float(margen_promedio):.2f}%",
        "top_margenes": top_margenes,
        
        # Compras
        "compras_recientes": compras_recientes,
        "compras_completadas": compras_completadas,
        "compras_pendientes": compras_pendientes,
        "compras_canceladas": compras_canceladas,
        "total_invertido": f"${float(total_invertido):,.2f}",
        "compras_completadas_monto": f"${float(compras_completadas_monto):,.2f}",
        
        # Devoluciones
        "devoluciones_recientes": devoluciones_recientes,
        "devoluciones_pendientes": devoluciones_pendientes,
        "devoluciones_aprobadas": devoluciones_aprobadas,
        "devoluciones_rechazadas": devoluciones_rechazadas,
        
        # Productos por proveedor
        "productos_por_proveedor": productos_por_proveedor,
        
        # Filtros
        "proveedores": Proveedor.objects.all(),
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "proveedor_id": proveedor_id,
        "estado_compra": estado_compra,
    }
    
    return render(request, "inventario/dashboard.html", context)

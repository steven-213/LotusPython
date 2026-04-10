from django.shortcuts import render
from django.db.models import DecimalField, IntegerField, Sum, F, Q, OuterRef, Subquery
from django.db.models.functions import Coalesce, TruncDay
from django.utils import timezone
from datetime import datetime, timedelta
from apps.sesiones.decorators import admin_required_session
from apps.ventas.models import Venta
from django.http import JsonResponse

from apps.inventario.models import (
    Producto,
    Inventario,
    Proveedor,
    MovimientoInventario
)



@admin_required_session
def sugerencia_pedido(request):
    proveedor_id = request.GET.get("proveedor")
    nombre_producto = request.GET.get("nombre")

    productos = Producto.objects.filter(activo=True)

    if proveedor_id:
        productos = productos.filter(proveedor_id=proveedor_id)

    if nombre_producto:
        productos = productos.filter(nombre__icontains=nombre_producto)

    sugerencias = []

    fecha_inicio = timezone.now() - timedelta(days=30)

    for producto in productos:
        stock = Inventario.objects.filter(
            producto=producto
        ).aggregate(total=Sum("stock"))["total"] or 0

        salidas = MovimientoInventario.objects.filter(
            producto=producto,
            tipo="SALIDA",
            fecha__gte=fecha_inicio
        ).aggregate(total=Sum("cantidad"))["total"] or 0

        cantidad_sugerida = salidas - stock
        if cantidad_sugerida < 0:
            cantidad_sugerida = 0

        if stock == 0:
            estado = "URGENTE"
            clase = "danger"
            prioridad = 1
        elif stock < 10:
            estado = "REFORZAR"
            clase = "warning"
            prioridad = 2
        else:
            estado = "OK"
            clase = "success"
            prioridad = 3

        sugerencias.append({
            "producto": producto,
            "stock": stock,
            "salidas": salidas,
            "cantidad_sugerida": cantidad_sugerida,
            "estado": estado,
            "clase": clase,
            "prioridad": prioridad
        })

    sugerencias.sort(key=lambda x: (x["prioridad"], -x["cantidad_sugerida"]))

    context = {
        "sugerencias": sugerencias,
        "proveedores": Proveedor.objects.all()
    }

    return render(request, "inventario/dashboard/control/lista.html", context)

@admin_required_session
def informe_inventario(request):
    # 1. Parámetros de filtrado
    rango = request.GET.get("rango", "personalizado")
    fecha_inicio_str = request.GET.get("fecha_inicio")
    fecha_fin_str = request.GET.get("fecha_fin")
    proveedor_id = request.GET.get("proveedor")

    hoy_dt = timezone.now()
    hoy = hoy_dt.date()
    fecha_inicio = None
    fecha_fin = None

    if rango == "hoy":
        fecha_inicio = fecha_fin = hoy
    elif rango == "7_dias":
        fecha_inicio = hoy - timedelta(days=7)
        fecha_fin = hoy
    elif fecha_inicio_str and fecha_fin_str:
        try:
            fecha_inicio = datetime.strptime(fecha_inicio_str, "%Y-%m-%d").date()
            fecha_fin = datetime.strptime(fecha_fin_str, "%Y-%m-%d").date()
        except:
            pass

    filtros = Q(producto__activo=True)
    if proveedor_id:
        filtros &= Q(producto__proveedor_id=proveedor_id)
    if fecha_inicio:
        filtros &= Q(fecha__date__gte=fecha_inicio)
    if fecha_fin:
        filtros &= Q(fecha__date__lte=fecha_fin)

    movimientos = MovimientoInventario.objects.filter(filtros)

    productos_stats = (
        movimientos.values("producto_id", "producto__nombre")
        .annotate(
            unidades_vendidas=Coalesce(
                Sum("cantidad", filter=Q(tipo="SALIDA")), 0, output_field=IntegerField()
            ),
            unidades_ingresadas=Coalesce(
                Sum("cantidad", filter=Q(tipo="INGRESO")), 0, output_field=IntegerField()
            ),
        )
        .order_by("-unidades_vendidas")
    )

    stock_por_producto = {
        i["producto"]: i["total"]
        for i in Inventario.objects.values("producto").annotate(total=Sum("stock"))
    }

    precio_reciente_subquery = Inventario.objects.filter(
        producto=OuterRef("producto")
    ).order_by("-fecha_ingreso").values("precio_venta")[:1]

    precios_por_producto = (
        Inventario.objects
        .annotate(precio=Subquery(precio_reciente_subquery))
        .values("producto", "precio")
    )
    precio_map = {p["producto"]: p["precio"] for p in precios_por_producto}

    ingresos_por_producto = (
        MovimientoInventario.objects
        .filter(tipo="SALIDA")
        .values("producto")
        .annotate(
            total=Sum(
                F("cantidad") * F("inventario__precio_venta"),
                output_field=DecimalField()
            )
        )
    )
    ingresos_map = {i["producto"]: i["total"] for i in ingresos_por_producto}

    resultado = []
    for p in productos_stats:
        p_id = p["producto_id"]
        resultado.append({
            "id_db": p_id,
            "nombre": p["producto__nombre"],
            "unidades_vendidas": p["unidades_vendidas"],
            "stock_actual": stock_por_producto.get(p_id, 0),
            "ingreso_total": ingresos_map.get(p_id, 0),
            "precio_reciente": precio_map.get(p_id, 0),
        })

    inicio_mes_actual = hoy_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    fin_mes_actual = hoy_dt

    ultimo_dia_mes_anterior = inicio_mes_actual - timedelta(days=1)
    inicio_mes_anterior = ultimo_dia_mes_anterior.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    fin_mes_anterior = ultimo_dia_mes_anterior.replace(hour=23, minute=59, second=59)

    ventas_actual = (
        Venta.objects.filter(fecha__range=(inicio_mes_actual, fin_mes_actual))
        .annotate(dia=TruncDay('fecha'))
        .values('dia')
        .annotate(total=Coalesce(Sum('total'), 0, output_field=DecimalField()))
        .order_by('dia')
    )

    ventas_anterior = (
        Venta.objects.filter(fecha__range=(inicio_mes_anterior, fin_mes_anterior))
        .annotate(dia=TruncDay('fecha'))
        .values('dia')
        .annotate(total=Coalesce(Sum('total'), 0, output_field=DecimalField()))
        .order_by('dia')
    )

    def formatear_ventas(queryset):
        return {item['dia'].day: float(item['total']) for item in queryset}

    actual_dict = formatear_ventas(ventas_actual)
    anterior_dict = formatear_ventas(ventas_anterior)

    dias_eje = list(range(1, 32))
    data_actual = [actual_dict.get(d, 0) for d in dias_eje]
    data_anterior = [anterior_dict.get(d, 0) for d in dias_eje]

    resultado = sorted(resultado, key=lambda x: x["unidades_vendidas"], reverse=True)
    mas_vendidos = resultado[:5]

    total_ingresos = sum([r["ingreso_total"] for r in resultado])
    total_unidades = sum([r["unidades_vendidas"] for r in resultado])
    total_stock = sum([r["stock_actual"] for r in resultado])

    context = {
        # Gráfico de líneas
        'dias': dias_eje,
        'data_actual': data_actual,
        'data_anterior': data_anterior,
        
        # Datos generales
        "productos_stats": resultado,
        "mas_vendidos": mas_vendidos,
        "menos_vendidos": resultado[::-1][:5],
        "totales": {
            "total_ingresos": total_ingresos,
            "total_unidades": total_unidades,
            "total_inventario": total_stock,
        },
        "proveedores": Proveedor.objects.all(),
        "hoy": hoy,
    }

    return render(request, "inventario/dashboard/control/informe.html", context)




@admin_required_session
def detalle_inventario_json(request, producto_id):
    # Buscamos todos los registros de inventario (lotes) de ese producto
    lotes = Inventario.objects.filter(producto_id=producto_id).order_by('-fecha_ingreso')
    
    if not lotes.exists():
        return JsonResponse({'error': 'No hay inventario registrado'}, status=404)

    nombre_producto = lotes.first().producto.nombre
    
    data = []
    for l in lotes:
        data.append({
            "lote": l.lote,
            "stock": l.stock,
            "precio_venta": str(l.precio_venta),
            "fecha": l.fecha_ingreso.strftime('%d/%m/%Y %H:%M')
        })
    
    return JsonResponse({
        'producto': nombre_producto,
        'detalles': data
    })
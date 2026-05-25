from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.db.models import Sum

from apps.inventario.models import Inventario, Producto
from apps.sesiones.decorators import admin_required_session


@admin_required_session
def sugerencia_pedido(request):
    """
    Sugerencia de compras basada en productos que tienen stock total crítico o en 0.
    """
    # Agrupamos el stock de los lotes por producto
    productos = Producto.objects.filter(activo=True).annotate(
        stock_total=Sum('inventario__stock')
    ).order_by('stock_total')
    
    # Aquí puedes filtrar los que tengan stock_total bajo o None (sin lotes)
    # Por ahora te dejamos el render listo para cuando crees tu plantilla:
    # return render(request, "inventario/dashboard/reportes/sugerencias.html", {"productos": productos})
    return redirect("inventario:dashboard")


@admin_required_session
def informe_inventario(request):
    """
    Vista para renderizar el informe general de inventario en HTML.
    """
    # return render(request, "inventario/dashboard/reportes/informe.html")
    return redirect("inventario:dashboard")


@admin_required_session
def detalle_inventario_json(request, producto_id):
    # 1. Agregamos select_related para evitar el problema N+1 con 'producto'
    # 2. Filtramos con stock__gt=0 para mostrar solo los lotes que tienen existencias reales
    lotes = (
        Inventario.objects
        .filter(producto_id=producto_id, stock__gt=0)
        .select_related("producto")
        .order_by("-fecha_ingreso")
    )

    if not lotes.exists():
        return JsonResponse({"error": "No hay stock disponible para este producto"}, status=404)

    nombre_producto = lotes.first().producto.nombre
    data = []
    
    for lote in lotes:
        data.append(
            {
                "lote": lote.lote,
                "stock": lote.stock,
                "precio_venta": str(lote.precio_venta),
                "fecha": lote.fecha_ingreso.strftime("%d/%m/%Y %H:%M"),
                # NUEVOS CAMPOS: Útiles para el frontend en alertas de vencimiento
                "fecha_vencimiento": lote.fecha_vencimiento.strftime("%d/%m/%Y") if lote.fecha_vencimiento else "N/A",
                "pao": lote.pao or "N/A",
            }
        )

    return JsonResponse({"producto": nombre_producto, "detalles": data})
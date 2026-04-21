from django.http import JsonResponse
from django.shortcuts import redirect

from apps.inventario.models import Inventario
from apps.sesiones.decorators import admin_required_session


@admin_required_session
def sugerencia_pedido(request):
    return redirect("inventario:dashboard")


@admin_required_session
def informe_inventario(request):
    return redirect("inventario:dashboard")


@admin_required_session
def detalle_inventario_json(request, producto_id):
    lotes = Inventario.objects.filter(producto_id=producto_id).order_by("-fecha_ingreso")

    if not lotes.exists():
        return JsonResponse({"error": "No hay inventario registrado"}, status=404)

    nombre_producto = lotes.first().producto.nombre
    data = []
    for lote in lotes:
        data.append(
            {
                "lote": lote.lote,
                "stock": lote.stock,
                "precio_venta": str(lote.precio_venta),
                "fecha": lote.fecha_ingreso.strftime("%d/%m/%Y %H:%M"),
            }
        )

    return JsonResponse({"producto": nombre_producto, "detalles": data})

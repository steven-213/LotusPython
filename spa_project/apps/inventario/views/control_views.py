from django.shortcuts import render
from django.db.models import Sum
from django.utils import timezone
from datetime import timedelta

from apps.inventario.models import (
    Producto,
    Inventario,
    Proveedor,
    MovimientoInventario
)
from apps.sesiones.decorators import admin_required_session


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

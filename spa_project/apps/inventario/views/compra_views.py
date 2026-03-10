from django.shortcuts import get_object_or_404, redirect, render

from apps.inventario.models import Compra, Proveedor
from apps.sesiones.decorators import admin_required_session


@admin_required_session
def compra_lista(request):
    compras = Compra.objects.select_related("proveedor").order_by("-fecha")
    return render(request, "inventario/compras/lista.html", {"compras": compras})


@admin_required_session
def compra_nueva(request):
    if request.method == "POST":
        proveedor_id = request.POST.get("proveedor_id")
        proveedor = get_object_or_404(Proveedor, id=proveedor_id)
        Compra.objects.create(
            proveedor=proveedor,
            total=request.POST.get("total") or 0,
            numero_factura=request.POST.get("numero_factura", ""),
        )
        return redirect("inventario:compra_lista")
    proveedores = Proveedor.objects.all()
    return render(request, "inventario/compras/nueva.html", {"proveedores": proveedores})


@admin_required_session
def compra_detalle(request, compra_id):
    compra = get_object_or_404(Compra.objects.select_related("proveedor"), id=compra_id)
    return render(request, "inventario/compras/detalle.html", {"compra": compra})

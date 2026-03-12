from apps.sesiones.decorators import admin_required_session
from django.shortcuts import render, redirect, get_object_or_404
from apps.inventario.models import Producto, DetalleCompra, Compra, Proveedor
from django.contrib import messages


@admin_required_session
def compra_lista(request):
    compras = Compra.objects.prefetch_related("detallecompra_set__unProducto__proveedor").order_by("-fechaCompra")
    return render(request, "inventario/compras/lista.html", {"compras": compras})


@admin_required_session
def compra_nueva(request):
    productos = Producto.objects.all()
    proveedores = Proveedor.objects.all()
    compra = None

    if request.method == "POST":
        proveedor_id = request.POST.get("proveedor_id")
        lote = request.POST.get("lote")
        fechaVencimiento = request.POST.get("fechaVencimiento")
        cantidad = request.POST.get("cantidad")
        precio_compra = request.POST.get("precio_compra")
        unProducto_id = request.POST.get("unProducto_id")

        if not all([proveedor_id, lote, fechaVencimiento, cantidad, precio_compra, unProducto_id]):
            messages.error(request, "Todos los campos son obligatorios.")
            return redirect("inventario:compra_nueva")

        # Crear compra nueva
        compra = Compra.objects.create(proveedor_id=proveedor_id, total=0)

        # Crear detalle
        DetalleCompra.objects.create(
            unCompra=compra,
            unProducto_id=unProducto_id,
            lote=lote,
            fechaVencimiento=fechaVencimiento,
            cantidad=cantidad,
            precio_compra=precio_compra
        )

        messages.success(request, "Compra creada correctamente")
        return redirect("inventario:compra_lista")

    return render(request, "inventario/compras/nueva.html", {
        "productos": productos,
        "proveedores": proveedores,
        "compra": compra
    })


@admin_required_session
def finalizar_compra(request):

    compra_id = request.session.get("compra_id")
    
    if not compra_id:
        return redirect("inventario:compra_lista")

    compra = Compra.objects.get(id=compra_id)

    if not compra.detallecompra_set.exists():
        messages.error(request, "No puedes finalizar la compra sin productos.")
        return redirect("inventario:compra_nueva")

    del request.session["compra_id"]

    messages.success(request, "Compra finalizada")

    return redirect("inventario:compra_lista")
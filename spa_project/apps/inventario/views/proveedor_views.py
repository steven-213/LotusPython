from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.inventario.models import Proveedor
from apps.inventario.services import anotar_stock_disponible
from apps.sesiones.decorators import admin_required_session


@admin_required_session
def proveedor_lista(request):
    query = request.GET.get("q", "")
    proveedores = Proveedor.objects.all()
    if query:
        proveedores = proveedores.filter(
            Q(nombre__icontains=query)
            | Q(empresa__icontains=query)
            | Q(nit__icontains=query)
            | Q(pais__icontains=query)
            | Q(correo__icontains=query)
        )
    return render(request, "inventario/dashboard/proveedores/lista.html", {"proveedores": proveedores, "query": query})


@admin_required_session
def proveedor_nuevo(request):
    if request.method == "POST":
        Proveedor.objects.create(
            nombre=request.POST.get("nombre"),
            empresa=request.POST.get("empresa", ""),
            telefono=request.POST.get("telefono", ""),
            correo=request.POST.get("correo", ""),
            direccion=request.POST.get("direccion", ""),
            nit=request.POST.get("nit", ""),
            pais=request.POST.get("pais", ""),
        )
        return redirect("inventario:proveedor_lista")
    return render(request, "inventario/dashboard/proveedores/nuevo.html")


@admin_required_session
def proveedor_detalle(request, proveedor_id):
    proveedor = get_object_or_404(Proveedor, id=proveedor_id)
    productos = anotar_stock_disponible(proveedor.producto_set.filter(activo=True))
    return render(
        request,
        "inventario/dashboard/proveedores/detalle.html",
        {"proveedor": proveedor, "productos": productos},
    )


@admin_required_session
def proveedor_editar(request, proveedor_id):
    proveedor = get_object_or_404(Proveedor, id=proveedor_id)
    if request.method == "POST":
        proveedor.nombre = request.POST.get("nombre")
        proveedor.empresa = request.POST.get("empresa", "")
        proveedor.telefono = request.POST.get("telefono", "")
        proveedor.correo = request.POST.get("correo", "")
        proveedor.direccion = request.POST.get("direccion", "")
        proveedor.nit = request.POST.get("nit", "")
        proveedor.pais = request.POST.get("pais", "")
        proveedor.save()
        return redirect("inventario:proveedor_lista")
    return render(request, "inventario/dashboard/proveedores/editar.html", {"proveedor": proveedor})


@admin_required_session
def proveedor_eliminar(request, proveedor_id):
    proveedor = get_object_or_404(Proveedor, id=proveedor_id)
    if request.method == "POST":
        proveedor.delete()
    return redirect("inventario:proveedor_lista")

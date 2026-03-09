from django.shortcuts import redirect, render

from apps.inventario.models import Proveedor
from apps.sesiones.decorators import admin_required_session


@admin_required_session
def proveedor_lista(request):
    proveedores = Proveedor.objects.all()
    return render(request, "inventario/proveedores/lista.html", {"proveedores": proveedores})


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
    return render(request, "inventario/proveedores/nuevo.html")

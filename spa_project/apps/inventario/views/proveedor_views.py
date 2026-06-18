from django.contrib import messages
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.inventario.models import Proveedor
from apps.inventario.services import anotar_stock_disponible
from apps.sesiones.decorators import admin_required_session


def _proveedor_duplicado(*, nombre, nit="", exclude_id=None):
    filtros = Q(nombre__iexact=nombre)
    nit = (nit or "").strip()
    if nit:
        filtros |= Q(nit__iexact=nit)

    proveedores = Proveedor.objects.filter(filtros)
    if exclude_id:
        proveedores = proveedores.exclude(id=exclude_id)
    return proveedores.first()


def _validar_datos_proveedor(request):
    nombre = (request.POST.get("nombre") or "").strip()
    telefono = (request.POST.get("telefono") or "").strip()
    correo = (request.POST.get("correo") or "").strip()
    direccion = (request.POST.get("direccion") or "").strip()
    nit = (request.POST.get("nit") or "").strip()
    pais = (request.POST.get("pais") or "Colombia").strip()

    if not (3 <= len(nombre) <= 50):
        raise ValueError("El nombre del proveedor debe tener entre 3 y 50 caracteres.")
    if not (7 <= len(telefono) <= 15) or not telefono.isdigit():
        raise ValueError("El telefono debe contener solo numeros y tener entre 7 y 15 digitos.")
    try:
        validate_email(correo)
    except ValidationError as exc:
        raise ValueError("Ingresa un correo electronico valido.") from exc
    if len(correo) > 100:
        raise ValueError("El correo no puede superar 100 caracteres.")
    if not (5 <= len(direccion) <= 100):
        raise ValueError("La direccion debe tener entre 5 y 100 caracteres.")
    if not (5 <= len(nit) <= 20) or not nit.isdigit():
        raise ValueError("El NIT debe contener solo numeros y tener entre 5 y 20 digitos.")

    return {
        "nombre": nombre,
        "telefono": telefono,
        "correo": correo,
        "direccion": direccion,
        "nit": nit,
        "pais": pais,
        "empresa": (request.POST.get("empresa") or "").strip(),
    }


@admin_required_session
def proveedor_lista(request):
    query = (request.GET.get("q", "") or "").strip()
    proveedores = Proveedor.objects.all()
    if query:
        if len(query) >= 3:
            proveedores = proveedores.filter(
                Q(nombre__icontains=query)
                | Q(empresa__icontains=query)
                | Q(nit__icontains=query)
                | Q(pais__icontains=query)
                | Q(correo__icontains=query)
            )
        else:
            messages.error(request, "La busqueda debe tener al menos 3 caracteres.")
    return render(request, "inventario/dashboard/proveedores/lista.html", {"proveedores": proveedores, "query": query})


@admin_required_session
def proveedor_nuevo(request):
    if request.method == "POST":
        try:
            datos = _validar_datos_proveedor(request)
        except ValueError as exc:
            messages.error(request, str(exc))
            return render(request, "inventario/dashboard/proveedores/nuevo.html")

        proveedor_existente = _proveedor_duplicado(nombre=datos["nombre"], nit=datos["nit"])
        if proveedor_existente:
            messages.error(request, "Ya existe un proveedor con ese nombre o NIT.")
            return render(request, "inventario/dashboard/proveedores/nuevo.html")

        Proveedor.objects.create(
            **datos,
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
        try:
            datos = _validar_datos_proveedor(request)
        except ValueError as exc:
            messages.error(request, str(exc))
            return render(request, "inventario/dashboard/proveedores/editar.html", {"proveedor": proveedor})

        proveedor_existente = _proveedor_duplicado(
            nombre=datos["nombre"],
            nit=datos["nit"],
            exclude_id=proveedor.id,
        )
        if proveedor_existente:
            messages.error(request, "Ya existe otro proveedor con ese nombre o NIT.")
            return render(request, "inventario/dashboard/proveedores/editar.html", {"proveedor": proveedor})

        proveedor.nombre = datos["nombre"]
        proveedor.empresa = datos["empresa"]
        proveedor.telefono = datos["telefono"]
        proveedor.correo = datos["correo"]
        proveedor.direccion = datos["direccion"]
        proveedor.nit = datos["nit"]
        proveedor.pais = datos["pais"]
        proveedor.save()
        return redirect("inventario:proveedor_lista")
    return render(request, "inventario/dashboard/proveedores/editar.html", {"proveedor": proveedor})


@admin_required_session
def proveedor_eliminar(request, proveedor_id):
    proveedor = get_object_or_404(Proveedor, id=proveedor_id)
    if request.method == "POST":
        proveedor.delete()
    return redirect("inventario:proveedor_lista")

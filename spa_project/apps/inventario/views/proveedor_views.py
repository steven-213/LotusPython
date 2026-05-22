from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.inventario.models import Proveedor
from apps.inventario.services import anotar_stock_disponible
from apps.common.validation import (
    validate_basic_text,
    validate_digits_string,
    validate_email,
)
from apps.sesiones.decorators import admin_required_session


def _proveedor_duplicado(*, nombre, nit="", correo="", exclude_id=None):
    filtros = Q(nombre__iexact=nombre)
    nit = (nit or "").strip()
    correo = (correo or "").strip()
    if nit:
        filtros |= Q(nit__iexact=nit)
    if correo:
        filtros |= Q(correo__iexact=correo)

    proveedores = Proveedor.objects.filter(filtros)
    if exclude_id:
        proveedores = proveedores.exclude(id=exclude_id)
    return proveedores.first()


def _render_proveedor_form(request, template_name, *, proveedor=None):
    context = {}
    if proveedor is not None:
        context["proveedor"] = proveedor
    return render(request, template_name, context)


@admin_required_session
def proveedor_lista(request):
    query = request.GET.get("q", "")
    proveedores = Proveedor.objects.all()
    if query:
        if len(query.strip()) < 3:
            messages.error(request, "La busqueda debe tener al menos 3 caracteres.")
            query = ""
        else:
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
        try:
            nombre = validate_basic_text(
                request.POST.get("nombre"),
                label="El nombre del proveedor",
                min_length=3,
                max_length=50,
            )
            telefono = validate_digits_string(
                request.POST.get("telefono"),
                label="El telefono del proveedor",
                min_length=7,
                max_length=15,
            )
            correo = validate_email(request.POST.get("correo"), max_length=100)
            direccion = validate_basic_text(
                request.POST.get("direccion"),
                label="La direccion del proveedor",
                min_length=5,
                max_length=100,
            )
            nit = validate_digits_string(
                request.POST.get("nit"),
                label="El NIT o documento del proveedor",
                min_length=5,
                max_length=20,
            )
            activo = request.POST.get("activo", "on") == "on"
        except ValueError as exc:
            messages.error(request, str(exc))
            return _render_proveedor_form(request, "inventario/dashboard/proveedores/nuevo.html")

        proveedor_existente = _proveedor_duplicado(nombre=nombre, nit=nit, correo=correo)
        if proveedor_existente:
            messages.error(request, "Ya existe un proveedor con ese nombre, correo o NIT.")
            return _render_proveedor_form(request, "inventario/dashboard/proveedores/nuevo.html")

        Proveedor.objects.create(
            nombre=nombre,
            empresa=request.POST.get("empresa", "").strip(),
            telefono=telefono,
            correo=correo,
            direccion=direccion,
            nit=nit,
            pais=request.POST.get("pais", "").strip(),
            activo=activo,
        )
        return redirect("inventario:proveedor_lista")
    return _render_proveedor_form(request, "inventario/dashboard/proveedores/nuevo.html")


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
            nombre = validate_basic_text(
                request.POST.get("nombre"),
                label="El nombre del proveedor",
                min_length=3,
                max_length=50,
            )
            telefono = validate_digits_string(
                request.POST.get("telefono"),
                label="El telefono del proveedor",
                min_length=7,
                max_length=15,
            )
            correo = validate_email(request.POST.get("correo"), max_length=100)
            direccion = validate_basic_text(
                request.POST.get("direccion"),
                label="La direccion del proveedor",
                min_length=5,
                max_length=100,
            )
            nit = validate_digits_string(
                request.POST.get("nit"),
                label="El NIT o documento del proveedor",
                min_length=5,
                max_length=20,
            )
            activo = request.POST.get("activo", "off") == "on"
        except ValueError as exc:
            messages.error(request, str(exc))
            return _render_proveedor_form(
                request,
                "inventario/dashboard/proveedores/editar.html",
                proveedor=proveedor,
            )

        proveedor_existente = _proveedor_duplicado(
            nombre=nombre,
            nit=nit,
            correo=correo,
            exclude_id=proveedor.id,
        )
        if proveedor_existente:
            messages.error(request, "Ya existe otro proveedor con ese nombre, correo o NIT.")
            return _render_proveedor_form(
                request,
                "inventario/dashboard/proveedores/editar.html",
                proveedor=proveedor,
            )

        proveedor.nombre = nombre
        proveedor.empresa = request.POST.get("empresa", "").strip()
        proveedor.telefono = telefono
        proveedor.correo = correo
        proveedor.direccion = direccion
        proveedor.nit = nit
        proveedor.pais = request.POST.get("pais", "").strip()
        proveedor.activo = activo
        proveedor.save()
        return redirect("inventario:proveedor_lista")
    return _render_proveedor_form(
        request,
        "inventario/dashboard/proveedores/editar.html",
        proveedor=proveedor,
    )


@admin_required_session
def proveedor_eliminar(request, proveedor_id):
    proveedor = get_object_or_404(Proveedor, id=proveedor_id)
    if request.method == "POST":
        proveedor.delete()
    return redirect("inventario:proveedor_lista")

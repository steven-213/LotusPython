from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from apps.common.currency import parse_money
from apps.citas.models import Profesional, Servicio
from apps.citas.storage import subir_imagen_servicio
from apps.sesiones.decorators import admin_required_session


def servicios_publicos(request):
    servicios = Servicio.objects.select_related("profesional").filter(activo=True).order_by("nombre")
    return render(request, "cliente/servicios.html", {"servicios": servicios})


@admin_required_session
def servicio_lista(request):
    servicios = Servicio.objects.select_related("profesional").order_by("nombre")
    return render(request, "citas/dashboard/servicios/lista.html", {"servicios": servicios})


@admin_required_session
def servicio_nuevo(request):
    profesionales = Profesional.objects.filter(activo=True).order_by("nombre")
    if request.method == "POST":
        profesional_id = request.POST.get("profesional_id")
        profesional_nombre = (request.POST.get("profesional_nombre") or "").strip()
        if profesional_id:
            profesional = get_object_or_404(Profesional, id=profesional_id)
        elif profesional_nombre:
            profesional, _ = Profesional.objects.get_or_create(nombre=profesional_nombre)
        else:
            messages.error(request, "Debes seleccionar o crear una profesional.")
            return render(
                request,
                "citas/dashboard/servicios/form.html",
                {"profesionales": profesionales},
            )
        imagen_url = subir_imagen_servicio(request.FILES.get("imagen"))
        Servicio.objects.create(
            nombre=request.POST.get("nombre"),
            descripcion=request.POST.get("descripcion", ""),
            imagen=imagen_url,
            precio=parse_money(request.POST.get("precio")),
            profesional=profesional,
            duracion_minutos=request.POST.get("duracion_minutos") or 60,
            activo=request.POST.get("activo") == "on",
        )
        messages.success(request, "Servicio creado correctamente.")
        return redirect("citas:servicio_lista")
    return render(
        request,
        "citas/dashboard/servicios/form.html",
        {"profesionales": profesionales},
    )


@admin_required_session
def servicio_editar(request, servicio_id):
    servicio = get_object_or_404(Servicio, id=servicio_id)
    profesionales = Profesional.objects.filter(activo=True).order_by("nombre")
    if request.method == "POST":
        profesional_id = request.POST.get("profesional_id")
        profesional_nombre = (request.POST.get("profesional_nombre") or "").strip()
        if profesional_id:
            profesional = get_object_or_404(Profesional, id=profesional_id)
        elif profesional_nombre:
            profesional, _ = Profesional.objects.get_or_create(nombre=profesional_nombre)
        else:
            messages.error(request, "Debes seleccionar o crear una profesional.")
            return render(
                request,
                "citas/dashboard/servicios/form.html",
                {"servicio": servicio, "profesionales": profesionales},
            )
        servicio.nombre = request.POST.get("nombre")
        servicio.descripcion = request.POST.get("descripcion", "")
        imagen_url = subir_imagen_servicio(request.FILES.get("imagen"))
        if imagen_url:
            servicio.imagen = imagen_url
        servicio.precio = parse_money(request.POST.get("precio"))
        servicio.duracion_minutos = request.POST.get("duracion_minutos") or 60
        servicio.activo = request.POST.get("activo") == "on"
        servicio.profesional = profesional
        servicio.save()
        messages.success(request, "Servicio actualizado.")
        return redirect("citas:servicio_lista")
    return render(
        request,
        "citas/dashboard/servicios/form.html",
        {"servicio": servicio, "profesionales": profesionales},
    )


@admin_required_session
def servicio_eliminar(request, servicio_id):
    servicio = get_object_or_404(Servicio, id=servicio_id)
    if request.method == "POST":
        servicio.activo = False
        servicio.save(update_fields=["activo"])
        messages.success(request, "Servicio desactivado.")
    return redirect("citas:servicio_lista")

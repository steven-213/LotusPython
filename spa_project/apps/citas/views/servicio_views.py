from django.shortcuts import get_object_or_404, redirect, render

from apps.citas.models import Servicio
from apps.sesiones.decorators import admin_required_session


def servicios_publicos(request):
    servicios = Servicio.objects.all().order_by("nombre")
    return render(request, "cliente/servicios.html", {"servicios": servicios})


@admin_required_session
def servicio_lista(request):
    servicios = Servicio.objects.all().order_by("nombre")
    return render(request, "citas/servicios/lista.html", {"servicios": servicios})


@admin_required_session
def servicio_nuevo(request):
    if request.method == "POST":
        Servicio.objects.create(
            nombre=request.POST.get("nombre"),
            descripcion=request.POST.get("descripcion", ""),
            precio=request.POST.get("precio") or 0,
            persona_servicio=request.POST.get("persona_servicio", ""),
        )
        return redirect("citas:servicio_lista")
    return render(request, "citas/servicios/form.html")


@admin_required_session
def servicio_editar(request, servicio_id):
    servicio = get_object_or_404(Servicio, id=servicio_id)
    if request.method == "POST":
        servicio.nombre = request.POST.get("nombre")
        servicio.descripcion = request.POST.get("descripcion", "")
        servicio.precio = request.POST.get("precio") or 0
        servicio.persona_servicio = request.POST.get("persona_servicio", "")
        servicio.save()
        return redirect("citas:servicio_lista")
    return render(request, "citas/servicios/form.html", {"servicio": servicio})


@admin_required_session
def servicio_eliminar(request, servicio_id):
    servicio = get_object_or_404(Servicio, id=servicio_id)
    if request.method == "POST":
        servicio.delete()
    return redirect("citas:servicio_lista")

from django.shortcuts import get_object_or_404, redirect, render

from apps.citas.models import Cita, Servicio
from apps.sesiones.decorators import admin_required_session, login_required_session
from apps.sesiones.models import Usuario


@admin_required_session
def calendario(request):
    return render(request, "citas/calendario.html")


@login_required_session
def agenda(request):
    citas = Cita.objects.select_related("cliente", "servicio").order_by("fecha_inicio")
    if request.session.get("usuario_rol") != Usuario.ROL_ADMIN:
        citas = citas.filter(cliente_id=request.session.get("usuario_id"))
    return render(request, "citas/lista.html", {"citas": citas})


@login_required_session
def cita_nueva(request):
    if request.method == "POST":
        cliente_id = request.POST.get("cliente_id") or request.session.get("usuario_id")
        servicio = get_object_or_404(Servicio, id=request.POST.get("servicio_id"))
        cliente = get_object_or_404(Usuario, id=cliente_id)
        Cita.objects.create(
            cliente=cliente,
            servicio=servicio,
            fecha_inicio=request.POST.get("fecha_inicio"),
            fecha_fin=request.POST.get("fecha_fin"),
            estado=request.POST.get("estado", "programada"),
            notas=request.POST.get("notas", ""),
        )
        return redirect("citas:agenda")
    servicios = Servicio.objects.all()
    return render(request, "citas/form.html", {"servicios": servicios})


@login_required_session
def cita_editar(request, cita_id):
    cita = get_object_or_404(Cita, id=cita_id)
    if request.method == "POST":
        cita.servicio = get_object_or_404(Servicio, id=request.POST.get("servicio_id"))
        cita.fecha_inicio = request.POST.get("fecha_inicio")
        cita.fecha_fin = request.POST.get("fecha_fin")
        cita.estado = request.POST.get("estado", "programada")
        cita.notas = request.POST.get("notas", "")
        cita.save()
        return redirect("citas:agenda")
    servicios = Servicio.objects.all()
    return render(request, "citas/form.html", {"cita": cita, "servicios": servicios})

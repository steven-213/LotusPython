from datetime import datetime
from django.shortcuts import get_object_or_404, redirect, render

from apps.citas.models import Reserva, Servicio
from apps.sesiones.decorators import admin_required_session, login_required_session
from apps.sesiones.models import Usuario


@admin_required_session
def calendario(request):
    return render(request, "citas/dashboard/calendario.html")


@login_required_session
def agenda(request):
    reservas = Reserva.objects.select_related("cliente", "servicio").order_by("fecha_inicio")
    if request.session.get("usuario_rol") != Usuario.ROL_ADMIN:
        reservas = reservas.filter(cliente_id=request.session.get("usuario_id"))
    return render(request, "citas/public/lista.html", {"reservas": reservas})


@login_required_session
def reserva_nueva(request):
    if request.method == "POST":
        cliente_id = request.POST.get("cliente_id") or request.session.get("usuario_id")
        servicio = get_object_or_404(Servicio, id=request.POST.get("servicio_id"))
        cliente = get_object_or_404(Usuario, id=cliente_id)
        # Convertir las fechas desde formato datetime-local (ISO format)
        fecha_inicio_str = request.POST.get("fecha_inicio")
        fecha_fin_str = request.POST.get("fecha_fin")
        fecha_inicio = datetime.fromisoformat(fecha_inicio_str) if fecha_inicio_str else None
        fecha_fin = datetime.fromisoformat(fecha_fin_str) if fecha_fin_str else None
        Reserva.objects.create(
            cliente=cliente,
            servicio=servicio,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            estado=request.POST.get("estado", "programada"),
            notas=request.POST.get("notas", ""),
        )
        return redirect("citas:agenda")
    servicios = Servicio.objects.all()
    return render(request, "citas/public/form.html", {"servicios": servicios})


@login_required_session
def reserva_editar(request, reserva_id):
    reserva = get_object_or_404(Reserva, id=reserva_id)
    if request.method == "POST":
        reserva.servicio = get_object_or_404(Servicio, id=request.POST.get("servicio_id"))
        # Convertir las fechas desde formato datetime-local (ISO format)
        fecha_inicio_str = request.POST.get("fecha_inicio")
        fecha_fin_str = request.POST.get("fecha_fin")
        reserva.fecha_inicio = datetime.fromisoformat(fecha_inicio_str) if fecha_inicio_str else reserva.fecha_inicio
        reserva.fecha_fin = datetime.fromisoformat(fecha_fin_str) if fecha_fin_str else reserva.fecha_fin
        reserva.estado = request.POST.get("estado", "programada")
        reserva.notas = request.POST.get("notas", "")
        reserva.save()
        return redirect("citas:agenda")
    servicios = Servicio.objects.all()
    return render(request, "citas/public/form.html", {"reserva": reserva, "servicios": servicios})

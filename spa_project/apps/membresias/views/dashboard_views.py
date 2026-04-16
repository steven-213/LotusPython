from decimal import Decimal

from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.membresias.forms import AsignarMembresiaForm, PlanMembresiaForm
from apps.membresias.models import MembresiaUsuario, PlanMembresia
from apps.membresias.services import (
    activar_plan_para_usuario,
    actualizar_membresias_vencidas,
    invalidar_cache_membresias_publicas,
)
from apps.sesiones.decorators import admin_required_session
from apps.sesiones.models import Usuario


def _obtener_admin_sesion(request):
    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        return None
    return Usuario.objects.filter(id=usuario_id).first()


def _base_dashboard_context():
    actualizar_membresias_vencidas()
    ahora = timezone.now()
    planes = PlanMembresia.objects.annotate(
        total_activos=Count(
            "membresias_usuario",
            filter=Q(
                membresias_usuario__estado=MembresiaUsuario.ESTADO_ACTIVA,
                membresias_usuario__fecha_fin__gte=ahora,
            ),
        ),
        total_historico=Count("membresias_usuario"),
    ).order_by("orden", "precio", "id")

    ingresos = MembresiaUsuario.objects.aggregate(
        total=Coalesce(Sum("precio_pagado"), Decimal("0"))
    )["total"]
    activas = MembresiaUsuario.objects.filter(
        estado=MembresiaUsuario.ESTADO_ACTIVA,
        fecha_fin__gte=ahora,
    ).count()
    vencidas = MembresiaUsuario.objects.filter(estado=MembresiaUsuario.ESTADO_VENCIDA).count()

    miembros_recientes = (
        MembresiaUsuario.objects.select_related("usuario", "plan")
        .order_by("-fecha_inicio", "-id")[:8]
    )
    top_planes = [plan for plan in planes if plan.total_activos][:3]

    return {
        "total_planes": planes.count(),
        "total_planes_activos": planes.filter(activo=True).count(),
        "total_membresias_activas": activas,
        "total_membresias_vencidas": vencidas,
        "ingresos_membresias": ingresos,
        "planes_resumen": planes[:3],
        "top_planes": top_planes,
        "miembros_recientes": miembros_recientes,
    }


def _render_miembros(request, *, form=None, status=200):
    actualizar_membresias_vencidas()
    estado = (request.GET.get("estado") or "activas").strip().lower()
    busqueda = (request.GET.get("q") or "").strip()

    membresias = MembresiaUsuario.objects.select_related("usuario", "plan", "creada_por")
    if estado == "activas":
        membresias = membresias.filter(
            estado=MembresiaUsuario.ESTADO_ACTIVA,
            fecha_fin__gte=timezone.now(),
        )
    elif estado == "canceladas":
        membresias = membresias.filter(estado=MembresiaUsuario.ESTADO_CANCELADA)
    elif estado == "vencidas":
        membresias = membresias.filter(estado=MembresiaUsuario.ESTADO_VENCIDA)

    if busqueda:
        filtros = (
            Q(usuario__nombre__icontains=busqueda)
            | Q(usuario__apellido__icontains=busqueda)
            | Q(plan__nombre__icontains=busqueda)
        )
        if busqueda.isdigit():
            filtros |= Q(usuario__documento=int(busqueda))
        membresias = membresias.filter(filtros)

    conteos = {
        "activas": MembresiaUsuario.objects.filter(
            estado=MembresiaUsuario.ESTADO_ACTIVA,
            fecha_fin__gte=timezone.now(),
        ).count(),
        "canceladas": MembresiaUsuario.objects.filter(
            estado=MembresiaUsuario.ESTADO_CANCELADA
        ).count(),
        "vencidas": MembresiaUsuario.objects.filter(
            estado=MembresiaUsuario.ESTADO_VENCIDA
        ).count(),
    }

    return render(
        request,
        "membresias/dashboard/miembro_lista.html",
        {
            "membresias": membresias.order_by("-fecha_inicio", "-id"),
            "estado_actual": estado,
            "busqueda": busqueda,
            "conteos": conteos,
            "assign_form": form or AsignarMembresiaForm(),
        },
        status=status,
    )


@admin_required_session
def dashboard(request):
    context = _base_dashboard_context()
    return render(request, "membresias/dashboard/dashboard.html", context)


@admin_required_session
def plan_lista(request):
    planes = PlanMembresia.objects.annotate(
        total_activos=Count(
            "membresias_usuario",
            filter=Q(
                membresias_usuario__estado=MembresiaUsuario.ESTADO_ACTIVA,
                membresias_usuario__fecha_fin__gte=timezone.now(),
            ),
        ),
        total_historico=Count("membresias_usuario"),
    ).order_by("orden", "precio", "id")
    return render(
        request,
        "membresias/dashboard/plan_lista.html",
        {
            "planes": planes,
        },
    )


@admin_required_session
def plan_nuevo(request):
    form = PlanMembresiaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        plan = form.save()
        invalidar_cache_membresias_publicas()
        messages.success(request, f"El plan {plan.nombre} fue creado correctamente.")
        return redirect("membresias:plan_lista")
    return render(
        request,
        "membresias/dashboard/plan_form.html",
        {
            "form": form,
            "page_title": "Nuevo plan",
            "page_description": "Crea planes editables para la vista publica y el dashboard.",
            "submit_label": "Crear plan",
        },
    )


@admin_required_session
def plan_editar(request, plan_id):
    plan = get_object_or_404(PlanMembresia, id=plan_id)
    form = PlanMembresiaForm(request.POST or None, instance=plan)
    if request.method == "POST" and form.is_valid():
        form.save()
        invalidar_cache_membresias_publicas()
        messages.success(request, f"El plan {plan.nombre} fue actualizado.")
        return redirect("membresias:plan_lista")
    return render(
        request,
        "membresias/dashboard/plan_form.html",
        {
            "form": form,
            "plan": plan,
            "page_title": f"Editar {plan.nombre}",
            "page_description": "Ajusta beneficios, precio y visibilidad del plan.",
            "submit_label": "Guardar cambios",
        },
    )


@admin_required_session
@require_POST
def plan_toggle(request, plan_id):
    plan = get_object_or_404(PlanMembresia, id=plan_id)
    plan.activo = not plan.activo
    plan.save(update_fields=["activo", "updated_at"])
    invalidar_cache_membresias_publicas()
    estado = "activo" if plan.activo else "inactivo"
    messages.success(request, f"El plan {plan.nombre} quedo {estado}.")
    return redirect("membresias:plan_lista")


@admin_required_session
def miembro_lista(request):
    return _render_miembros(request)


@admin_required_session
@require_POST
def miembro_asignar(request):
    form = AsignarMembresiaForm(request.POST)
    if form.is_valid():
        usuario = form.cleaned_data["usuario"]
        plan = form.cleaned_data["plan"]
        notas = form.cleaned_data["notas"]
        admin_actor = _obtener_admin_sesion(request)
        activar_plan_para_usuario(
            usuario,
            plan,
            actor=admin_actor,
            origen=MembresiaUsuario.ORIGEN_ADMIN,
            notas=notas or "Asignada desde el dashboard administrativo.",
        )
        messages.success(
            request,
            f"Se asigno la membresia {plan.nombre} a {usuario.nombre} {usuario.apellido}.",
        )
        return redirect("membresias:miembro_lista")
    return _render_miembros(request, form=form, status=400)


@admin_required_session
@require_POST
def miembro_cancelar(request, membresia_id):
    membresia = get_object_or_404(
        MembresiaUsuario.objects.select_related("usuario", "plan"),
        id=membresia_id,
    )
    if membresia.estado != MembresiaUsuario.ESTADO_ACTIVA:
        messages.info(request, "La membresia ya no estaba activa.")
        return redirect("membresias:miembro_lista")

    membresia.estado = MembresiaUsuario.ESTADO_CANCELADA
    membresia.fecha_fin = timezone.now()
    membresia.save(update_fields=["estado", "fecha_fin", "updated_at"])
    messages.success(
        request,
        f"La membresia de {membresia.usuario.nombre} en el plan {membresia.plan.nombre} fue cancelada.",
    )
    return redirect("membresias:miembro_lista")

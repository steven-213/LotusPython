from datetime import timedelta

from django.utils import timezone

from apps.membresias.models import MembresiaUsuario


def actualizar_membresias_vencidas(*, usuario_id=None):
    filtros = {
        "estado": MembresiaUsuario.ESTADO_ACTIVA,
        "fecha_fin__lt": timezone.now(),
    }
    if usuario_id is not None:
        filtros["usuario_id"] = usuario_id
    return MembresiaUsuario.objects.filter(**filtros).update(
        estado=MembresiaUsuario.ESTADO_VENCIDA
    )


def obtener_membresia_activa(usuario):
    if not usuario:
        return None

    actualizar_membresias_vencidas(usuario_id=usuario.id)
    return (
        MembresiaUsuario.objects.select_related("plan")
        .filter(
            usuario=usuario,
            estado=MembresiaUsuario.ESTADO_ACTIVA,
            fecha_fin__gte=timezone.now(),
        )
        .order_by("-fecha_inicio", "-id")
        .first()
    )


def activar_plan_para_usuario(usuario, plan, *, actor=None, origen=MembresiaUsuario.ORIGEN_WEB, notas=""):
    ahora = timezone.now()
    MembresiaUsuario.objects.filter(
        usuario=usuario,
        estado=MembresiaUsuario.ESTADO_ACTIVA,
        fecha_fin__gte=ahora,
    ).update(estado=MembresiaUsuario.ESTADO_REEMPLAZADA)

    return MembresiaUsuario.objects.create(
        usuario=usuario,
        plan=plan,
        estado=MembresiaUsuario.ESTADO_ACTIVA,
        fecha_inicio=ahora,
        fecha_fin=ahora + timedelta(days=plan.duracion_dias),
        precio_pagado=plan.precio,
        origen=origen,
        notas=notas,
        creada_por=actor,
    )


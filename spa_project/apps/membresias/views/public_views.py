from django.contrib import messages
from django.core.cache import cache
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.common.seo import apply_public_page_cache_headers, serialize_structured_data
from apps.membresias.models import MembresiaUsuario, PlanMembresia
from apps.membresias.services import (
    PUBLIC_MEMBERSHIPS_CACHE_TIMEOUT,
    activar_plan_para_usuario,
    membresias_publicas_cache_key,
    obtener_membresia_activa,
)
from apps.sesiones.decorators import login_required_session
from apps.sesiones.models import Usuario


def _obtener_usuario_sesion(request):
    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        return None
    return Usuario.objects.filter(id=usuario_id).first()


def _obtener_payload_planes_publicos():
    cache_key = membresias_publicas_cache_key()
    payload = cache.get(cache_key)
    if payload is not None:
        return payload

    estilos = ["esencia", "ritual", "aura"]
    planes = list(
        PlanMembresia.objects.filter(activo=True)
        .values(
            "id",
            "nombre",
            "subtitulo",
            "descripcion",
            "beneficios",
            "precio",
            "duracion_dias",
            "insignia",
            "destacado",
        )
        .order_by("orden", "precio", "id")
    )

    planes_display = []
    for indice, plan in enumerate(planes):
        planes_display.append(
            {
                **plan,
                "beneficios_lista": [
                    linea.strip()
                    for linea in (plan.get("beneficios") or "").splitlines()
                    if linea.strip()
                ],
                "estilo": estilos[indice % len(estilos)],
            }
        )

    payload = {
        "planes_display": planes_display,
        "structured_data_json": serialize_structured_data(
            {
                "@context": "https://schema.org",
                "@type": "OfferCatalog",
                "name": "Membresias Lotus Dream Spa",
                "itemListElement": [
                    {
                        "@type": "Offer",
                        "name": plan["nombre"],
                        "description": plan["subtitulo"] or plan["descripcion"],
                        "priceCurrency": "COP",
                        "price": str(plan["precio"]),
                    }
                    for plan in planes
                ],
            }
        ),
    }
    cache.set(cache_key, payload, PUBLIC_MEMBERSHIPS_CACHE_TIMEOUT)
    return payload


def membresias_publicas(request):
    usuario = _obtener_usuario_sesion(request)
    membresia_actual = obtener_membresia_activa(usuario) if usuario else None
    payload = _obtener_payload_planes_publicos()
    planes_display = [
        {
            **plan,
            "es_actual": bool(membresia_actual and membresia_actual.plan_id == plan["id"]),
        }
        for plan in payload["planes_display"]
    ]

    response = render(
        request,
        "membresias/public/lista.html",
        {
            "planes_display": planes_display,
            "membresia_actual": membresia_actual,
            "usuario": usuario,
            "meta_title": "Membresias | Lotus Dream Spa",
            "meta_description": (
                "Conoce los planes de membresia de Lotus Dream Spa y activa el que mejor se "
                "adapte a tu ritmo de bienestar."
            ),
            "structured_data_json": payload["structured_data_json"],
        },
    )
    return apply_public_page_cache_headers(response)


@login_required_session
@require_POST
def activar_membresia(request, plan_id):
    usuario = _obtener_usuario_sesion(request)
    plan = get_object_or_404(PlanMembresia, id=plan_id, activo=True)

    membresia_actual = obtener_membresia_activa(usuario)
    if membresia_actual and membresia_actual.plan_id == plan.id:
        messages.info(request, f"Ya tienes activa la membresia {plan.nombre}.")
        return redirect("membresias:membresias")

    activar_plan_para_usuario(
        usuario,
        plan,
        actor=usuario,
        origen=MembresiaUsuario.ORIGEN_WEB,
        notas="Activada desde la pagina publica de membresias.",
    )
    messages.success(request, f"Tu membresia {plan.nombre} ya quedo activa.")
    return redirect("membresias:membresias")

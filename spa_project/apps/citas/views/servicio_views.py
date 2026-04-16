from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.shortcuts import get_object_or_404, redirect, render

from apps.common.seo import apply_public_page_cache_headers, serialize_structured_data
from apps.common.currency import parse_money
from apps.citas.models import Profesional, Servicio
from apps.citas.storage import subir_imagen_servicio
from apps.sesiones.decorators import admin_required_session


PUBLIC_SERVICES_CACHE_KEY = "public:servicios:activos"
PUBLIC_SERVICES_CACHE_TIMEOUT = getattr(settings, "PUBLIC_CATALOG_CACHE_TIMEOUT", 60)


def _cargar_servicios_publicos():
    return list(
        Servicio.objects.select_related("profesional")
        .only(
            "id",
            "nombre",
            "descripcion",
            "imagen",
            "precio",
            "duracion_minutos",
            "profesional__nombre",
        )
        .filter(activo=True)
        .order_by("nombre")
    )


def servicios_publicos(request):
    servicios = cache.get(PUBLIC_SERVICES_CACHE_KEY)
    if servicios is None:
        servicios = _cargar_servicios_publicos()
        cache.set(PUBLIC_SERVICES_CACHE_KEY, servicios, PUBLIC_SERVICES_CACHE_TIMEOUT)

    structured_data = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "Servicios Lotus Dream Spa",
        "description": (
            "Catálogo público de servicios de Lotus Dream Spa para reservar "
            "experiencias de bienestar, belleza y cuidado personal."
        ),
        "mainEntity": {
            "@type": "ItemList",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": posicion,
                    "item": {
                        "@type": "Service",
                        "name": servicio.nombre,
                        "description": servicio.descripcion or "Servicio disponible en Lotus Dream Spa.",
                        "provider": {
                            "@type": "BeautySalon",
                            "name": "Lotus Dream Spa",
                        },
                        "offers": {
                            "@type": "Offer",
                            "price": servicio.precio,
                            "priceCurrency": "COP",
                            "availability": "https://schema.org/InStock",
                        },
                    },
                }
                for posicion, servicio in enumerate(servicios[:12], start=1)
            ],
        },
    }

    response = render(
        request,
        "cliente/servicios.html",
        {
            "servicios": servicios,
            "meta_title": "Servicios | Lotus Dream Spa",
            "meta_description": (
                "Explora servicios de spa, bienestar y belleza en Lotus Dream "
                "Spa. Compara precio, duración y agenda la experiencia ideal."
            ),
            "structured_data_json": serialize_structured_data(structured_data),
        },
    )
    return apply_public_page_cache_headers(response)


@admin_required_session
def servicio_lista(request):
    servicios = Servicio.objects.select_related("profesional").order_by("nombre")
    return render(request, "citas/dashboard/servicios/lista.html", {"servicios": servicios})


@admin_required_session
def servicio_nuevo(request):
    profesionales = Profesional.objects.filter(activo=True).order_by("nombre")
    if request.method == "POST":
        nombre = (request.POST.get("nombre") or "").strip()
        if not nombre:
            messages.error(request, "Debes ingresar el nombre del servicio.")
            return render(
                request,
                "citas/dashboard/servicios/form.html",
                {"profesionales": profesionales},
            )

        profesional_id = request.POST.get("profesional_id")
        profesional_nombre = (request.POST.get("profesional_nombre") or "").strip()
        if profesional_id:
            profesional = get_object_or_404(Profesional, id=profesional_id)
        elif profesional_nombre:
            profesional = Profesional.objects.filter(nombre__iexact=profesional_nombre).first()
            if not profesional:
                profesional = Profesional.objects.create(nombre=profesional_nombre)
        else:
            messages.error(request, "Debes seleccionar o crear una profesional.")
            return render(
                request,
                "citas/dashboard/servicios/form.html",
                {"profesionales": profesionales},
            )

        if Servicio.objects.filter(nombre__iexact=nombre, profesional=profesional).exists():
            messages.error(
                request,
                "Ya existe un servicio con ese nombre para la profesional seleccionada.",
            )
            return render(
                request,
                "citas/dashboard/servicios/form.html",
                {"profesionales": profesionales},
            )
        imagen_url = subir_imagen_servicio(request.FILES.get("imagen"))
        Servicio.objects.create(
            nombre=nombre,
            descripcion=request.POST.get("descripcion", ""),
            imagen=imagen_url,
            precio=parse_money(request.POST.get("precio")),
            profesional=profesional,
            duracion_minutos=request.POST.get("duracion_minutos") or 60,
            activo=request.POST.get("activo") == "on",
        )
        cache.delete(PUBLIC_SERVICES_CACHE_KEY)
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
        nombre = (request.POST.get("nombre") or "").strip()
        if not nombre:
            messages.error(request, "Debes ingresar el nombre del servicio.")
            return render(
                request,
                "citas/dashboard/servicios/form.html",
                {"servicio": servicio, "profesionales": profesionales},
            )

        profesional_id = request.POST.get("profesional_id")
        profesional_nombre = (request.POST.get("profesional_nombre") or "").strip()
        if profesional_id:
            profesional = get_object_or_404(Profesional, id=profesional_id)
        elif profesional_nombre:
            profesional = Profesional.objects.filter(nombre__iexact=profesional_nombre).first()
            if not profesional:
                profesional = Profesional.objects.create(nombre=profesional_nombre)
        else:
            messages.error(request, "Debes seleccionar o crear una profesional.")
            return render(
                request,
                "citas/dashboard/servicios/form.html",
                {"servicio": servicio, "profesionales": profesionales},
            )

        if (
            Servicio.objects.filter(nombre__iexact=nombre, profesional=profesional)
            .exclude(id=servicio.id)
            .exists()
        ):
            messages.error(
                request,
                "Ya existe otro servicio con ese nombre para la profesional seleccionada.",
            )
            return render(
                request,
                "citas/dashboard/servicios/form.html",
                {"servicio": servicio, "profesionales": profesionales},
            )

        servicio.nombre = nombre
        servicio.descripcion = request.POST.get("descripcion", "")
        imagen_url = subir_imagen_servicio(request.FILES.get("imagen"))
        if imagen_url:
            servicio.imagen = imagen_url
        servicio.precio = parse_money(request.POST.get("precio"))
        servicio.duracion_minutos = request.POST.get("duracion_minutos") or 60
        servicio.activo = request.POST.get("activo") == "on"
        servicio.profesional = profesional
        servicio.save()
        cache.delete(PUBLIC_SERVICES_CACHE_KEY)
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
        cache.delete(PUBLIC_SERVICES_CACHE_KEY)
        messages.success(request, "Servicio desactivado.")
    return redirect("citas:servicio_lista")

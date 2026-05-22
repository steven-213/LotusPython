from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.shortcuts import get_object_or_404, redirect, render
from pathlib import Path
from types import SimpleNamespace

from apps.common.currency import parse_money
from apps.common.seo import apply_public_page_cache_headers, serialize_structured_data
from apps.common.validation import validate_basic_text, validate_name, validate_positive_int
from apps.citas.models import Profesional, Servicio
from apps.citas.storage import subir_imagen_servicio
from apps.sesiones.decorators import admin_required_session


PUBLIC_SERVICES_CACHE_KEY = "public:servicios:activos"
PUBLIC_SERVICES_CACHE_TIMEOUT = getattr(settings, "PUBLIC_CATALOG_CACHE_TIMEOUT", 60)
PUBLIC_SERVICES_CACHE_VERSION_KEY = "public:servicios:version"
ALLOWED_SERVICE_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_SERVICE_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_SERVICE_IMAGE_BYTES = 500 * 1024


def _servicios_publicos_cache_key():
    version = cache.get_or_set(PUBLIC_SERVICES_CACHE_VERSION_KEY, 1, None)
    return f"{PUBLIC_SERVICES_CACHE_KEY}:v{version}"


def _invalidar_cache_servicios_publicos():
    try:
        cache.incr(PUBLIC_SERVICES_CACHE_VERSION_KEY)
    except ValueError:
        cache.set(PUBLIC_SERVICES_CACHE_VERSION_KEY, 2, None)


def _cargar_servicios_publicos():
    servicios = list(
        Servicio.objects.select_related("profesional")
        .values(
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
    return [SimpleNamespace(**servicio) for servicio in servicios]


def _build_servicios_structured_data(servicios):
    return {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "Servicios Lotus Dream Spa",
        "description": (
            "Catalogo publico de servicios de Lotus Dream Spa para reservar "
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


def _obtener_payload_servicios_publicos():
    cache_key = _servicios_publicos_cache_key()
    payload = cache.get(cache_key)
    if payload is not None:
        return payload

    servicios = _cargar_servicios_publicos()
    payload = {
        "servicios": servicios,
        "structured_data_json": serialize_structured_data(
            _build_servicios_structured_data(servicios)
        ),
    }
    cache.set(cache_key, payload, PUBLIC_SERVICES_CACHE_TIMEOUT)
    return payload


def servicios_publicos(request):
    payload = _obtener_payload_servicios_publicos()
    servicios = payload["servicios"]

    response = render(
        request,
        "cliente/servicios.html",
        {
            "servicios": servicios,
            "meta_title": "Servicios | Lotus Dream Spa",
            "meta_description": (
                "Explora servicios de spa, bienestar y belleza en Lotus Dream "
                "Spa. Compara precio, duracion y agenda la experiencia ideal."
            ),
            "structured_data_json": payload["structured_data_json"],
        },
    )
    return apply_public_page_cache_headers(response)


def _render_servicio_form(request, *, profesionales, servicio=None):
    context = {"profesionales": profesionales}
    if servicio is not None:
        context["servicio"] = servicio
    return render(request, "citas/dashboard/servicios/form.html", context)


def _validar_imagen_servicio(archivo, *, required):
    if not archivo:
        if required:
            raise ValueError("Debes cargar una imagen para el servicio.")
        return

    extension = Path(getattr(archivo, "name", "")).suffix.lower()
    content_type = str(getattr(archivo, "content_type", "") or "").lower()
    if extension not in ALLOWED_SERVICE_IMAGE_EXTENSIONS and content_type not in ALLOWED_SERVICE_IMAGE_TYPES:
        raise ValueError("La imagen debe estar en formato JPG, PNG o WEBP.")
    if getattr(archivo, "size", 0) > MAX_SERVICE_IMAGE_BYTES:
        raise ValueError("La imagen no puede superar 500 KB.")


def _resolver_profesional_form(request):
    profesional_id = (request.POST.get("profesional_id") or "").strip()
    profesional_nombre = (request.POST.get("profesional_nombre") or "").strip()

    if profesional_id and profesional_nombre:
        raise ValueError("Debes seleccionar una profesional existente o crear una nueva, no ambas opciones.")
    if profesional_id:
        profesional = Profesional.objects.filter(id=profesional_id).first()
        if not profesional:
            raise ValueError("La profesional seleccionada no existe.")
        return profesional
    if profesional_nombre:
        profesional_nombre = validate_name(
            profesional_nombre,
            label="El nombre de la profesional",
            min_length=3,
            max_length=50,
        )
        profesional = Profesional.objects.filter(nombre__iexact=profesional_nombre).first()
        if profesional:
            return profesional
        return Profesional.objects.create(nombre=profesional_nombre)
    raise ValueError("Debes seleccionar o crear una profesional.")


@admin_required_session
def servicio_lista(request):
    servicios = Servicio.objects.select_related("profesional").order_by("nombre")
    return render(request, "citas/dashboard/servicios/lista.html", {"servicios": servicios})


@admin_required_session
def servicio_nuevo(request):
    profesionales = Profesional.objects.filter(activo=True).order_by("nombre")
    if request.method == "POST":
        try:
            nombre = validate_basic_text(
                request.POST.get("nombre"),
                label="El nombre del servicio",
                min_length=3,
                max_length=50,
            )
            descripcion = validate_basic_text(
                request.POST.get("descripcion"),
                label="La descripcion del servicio",
                min_length=5,
                max_length=255,
            )
            profesional = _resolver_profesional_form(request)
            try:
                precio = parse_money(request.POST.get("precio"), default=None)
            except Exception as exc:
                raise ValueError("El precio del servicio debe ser un valor valido.") from exc
            if precio <= 0:
                raise ValueError("El precio del servicio debe ser mayor a cero.")
            duracion_minutos = validate_positive_int(
                request.POST.get("duracion_minutos"),
                label="La duracion del servicio",
                min_value=15,
            )
            if Servicio.objects.filter(nombre__iexact=nombre).exists():
                raise ValueError("Ya existe un servicio con ese nombre.")
            imagen = request.FILES.get("imagen")
            _validar_imagen_servicio(imagen, required=True)
        except Exception as exc:
            messages.error(request, str(exc))
            return _render_servicio_form(request, profesionales=profesionales)

        imagen_url = subir_imagen_servicio(imagen)
        if not imagen_url:
            messages.error(request, "No fue posible guardar la imagen del servicio.")
            return _render_servicio_form(request, profesionales=profesionales)

        Servicio.objects.create(
            nombre=nombre,
            descripcion=descripcion,
            imagen=imagen_url,
            precio=precio,
            profesional=profesional,
            duracion_minutos=duracion_minutos,
            activo=request.POST.get("activo") == "on",
        )
        _invalidar_cache_servicios_publicos()
        messages.success(request, "Servicio creado correctamente.")
        return redirect("citas:servicio_lista")
    return _render_servicio_form(request, profesionales=profesionales)


@admin_required_session
def servicio_editar(request, servicio_id):
    servicio = get_object_or_404(Servicio, id=servicio_id)
    profesionales = Profesional.objects.filter(activo=True).order_by("nombre")
    if request.method == "POST":
        try:
            nombre = validate_basic_text(
                request.POST.get("nombre"),
                label="El nombre del servicio",
                min_length=3,
                max_length=50,
            )
            descripcion = validate_basic_text(
                request.POST.get("descripcion"),
                label="La descripcion del servicio",
                min_length=5,
                max_length=255,
            )
            profesional = _resolver_profesional_form(request)
            try:
                precio = parse_money(request.POST.get("precio"), default=None)
            except Exception as exc:
                raise ValueError("El precio del servicio debe ser un valor valido.") from exc
            if precio <= 0:
                raise ValueError("El precio del servicio debe ser mayor a cero.")
            duracion_minutos = validate_positive_int(
                request.POST.get("duracion_minutos"),
                label="La duracion del servicio",
                min_value=15,
            )
            if Servicio.objects.filter(nombre__iexact=nombre).exclude(id=servicio.id).exists():
                raise ValueError("Ya existe otro servicio con ese nombre.")
            imagen = request.FILES.get("imagen")
            _validar_imagen_servicio(imagen, required=not bool(servicio.imagen))
        except Exception as exc:
            messages.error(request, str(exc))
            return _render_servicio_form(request, servicio=servicio, profesionales=profesionales)

        servicio.nombre = nombre
        servicio.descripcion = descripcion
        imagen_url = subir_imagen_servicio(imagen)
        if imagen_url:
            servicio.imagen = imagen_url
        servicio.precio = precio
        servicio.duracion_minutos = duracion_minutos
        servicio.activo = request.POST.get("activo") == "on"
        servicio.profesional = profesional
        servicio.save()
        _invalidar_cache_servicios_publicos()
        messages.success(request, "Servicio actualizado.")
        return redirect("citas:servicio_lista")
    return _render_servicio_form(request, servicio=servicio, profesionales=profesionales)


@admin_required_session
def servicio_eliminar(request, servicio_id):
    servicio = get_object_or_404(Servicio, id=servicio_id)
    if request.method == "POST":
        servicio.activo = False
        servicio.save(update_fields=["activo"])
        _invalidar_cache_servicios_publicos()
        messages.success(request, "Servicio desactivado.")
    return redirect("citas:servicio_lista")

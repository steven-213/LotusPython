import json

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.templatetags.static import static
from django.utils.cache import patch_cache_control, patch_vary_headers


DEFAULT_SITE_NAME = "Lotus Dream Spa"
DEFAULT_META_DESCRIPTION = (
    "Spa en Colombia con servicios de bienestar, cuidado personal y una tienda "
    "de productos para continuar tu ritual en casa."
)
DEFAULT_OG_IMAGE = "img/logo.png"

NOINDEX_VIEWS = {
    ("sesiones", "login"),
    ("sesiones", "logout"),
    ("sesiones", "registro"),
    ("sesiones", "perfil"),
    ("inventario", "resultado"),
    ("citas", "agenda"),
    ("citas", "reserva_nueva"),
    ("citas", "reserva_confirmada"),
    ("citas", "reserva_detalle"),
    ("citas", "reserva_editar"),
}


def build_absolute_url(request, path=""):
    base_url = (getattr(settings, "APP_BASE_URL", "") or "").strip().rstrip("/")
    if path and str(path).startswith(("http://", "https://")):
        return str(path)

    normalized_path = str(path or request.path or "/")
    if not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path}"

    if base_url:
        return f"{base_url}{normalized_path}"

    return request.build_absolute_uri(normalized_path)


def serialize_structured_data(payload):
    if not payload:
        return ""
    return json.dumps(payload, ensure_ascii=False, cls=DjangoJSONEncoder)


def build_site_meta(request, *, show_admin_sidebar=False):
    resolver_match = getattr(request, "resolver_match", None)
    namespace = getattr(resolver_match, "namespace", "") or ""
    url_name = getattr(resolver_match, "url_name", "") or ""
    default_canonical_url = build_absolute_url(request, request.path)
    default_og_image = build_absolute_url(request, static(DEFAULT_OG_IMAGE))
    site_url = build_absolute_url(request, "/")
    is_indexable = not show_admin_sidebar and (namespace, url_name) not in NOINDEX_VIEWS

    site_schema = {
        "@context": "https://schema.org",
        "@type": "BeautySalon",
        "name": DEFAULT_SITE_NAME,
        "url": site_url,
        "logo": default_og_image,
        "image": default_og_image,
        "description": DEFAULT_META_DESCRIPTION,
    }

    return {
        "site_name": DEFAULT_SITE_NAME,
        "default_meta_description": DEFAULT_META_DESCRIPTION,
        "default_meta_robots": "index,follow" if is_indexable else "noindex,nofollow",
        "default_canonical_url": default_canonical_url,
        "default_og_image": default_og_image,
        "site_structured_data_json": serialize_structured_data(site_schema),
    }


def apply_public_page_cache_headers(response):
    patch_cache_control(
        response,
        private=True,
        max_age=getattr(settings, "PUBLIC_PAGE_CACHE_TIMEOUT", 300),
    )
    patch_vary_headers(response, ("Cookie",))
    return response

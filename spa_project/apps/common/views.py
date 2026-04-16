from django.http import HttpResponse

from apps.common.seo import build_absolute_url


def robots_txt(request):
    sitemap_url = build_absolute_url(request, "/sitemap.xml")
    contenido = "\n".join(
        [
            "User-agent: *",
            "Allow: /",
            "Disallow: /admin/",
            "Disallow: /login/",
            "Disallow: /logout/",
            "Disallow: /registro/",
            "Disallow: /perfil/",
            "Disallow: /ventas/",
            "Disallow: /inventario/productos/",
            "Disallow: /inventario/compras/",
            "Disallow: /inventario/proveedores/",
            "Disallow: /inventario/control/",
            "Disallow: /inventario/devoluciones/",
            "Disallow: /inventario/catalogo/procesar-pago/",
            "Disallow: /inventario/catalogo/resultado/",
            "Disallow: /citas/calendario/",
            "Disallow: /citas/agenda/",
            "Disallow: /citas/api/",
            "Disallow: /citas/pagos/",
            f"Sitemap: {sitemap_url}",
        ]
    )
    return HttpResponse(contenido, content_type="text/plain; charset=utf-8")

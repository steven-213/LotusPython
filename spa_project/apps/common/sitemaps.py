from django.contrib.sitemaps import Sitemap
from django.db.models import Max
from django.urls import reverse

from apps.citas.models import Servicio
from apps.inventario.models import Producto


class StaticViewSitemap(Sitemap):
    priority = 0.8
    changefreq = "weekly"

    def items(self):
        return [
            "sesiones:home",
            "sesiones:conocenos",
            "citas:servicios_publicos",
            "inventario:productos_publicos",
        ]

    def location(self, item):
        return reverse(item)


class ServiciosPublicosSitemap(Sitemap):
    priority = 0.7
    changefreq = "daily"

    def items(self):
        return ["citas:servicios_publicos"]

    def location(self, item):
        return reverse(item)

    def lastmod(self, item):
        return Servicio.objects.filter(activo=True).aggregate(lastmod=Max("updated_at"))["lastmod"]


class ProductosPublicosSitemap(Sitemap):
    priority = 0.7
    changefreq = "daily"

    def items(self):
        return ["inventario:productos_publicos"]

    def location(self, item):
        return reverse(item)

    def lastmod(self, item):
        return Producto.objects.filter(activo=True).aggregate(lastmod=Max("updated_at"))["lastmod"]


sitemaps = {
    "static": StaticViewSitemap(),
    "servicios": ServiciosPublicosSitemap(),
    "productos": ProductosPublicosSitemap(),
}

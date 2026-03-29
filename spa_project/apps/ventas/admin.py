from django.contrib import admin

from apps.ventas.models import (
    DetalleVenta,
    SolicitudDevolucionVenta,
    ValidacionVenta,
    Venta,
)

admin.site.register(Venta)
admin.site.register(DetalleVenta)
admin.site.register(ValidacionVenta)
admin.site.register(SolicitudDevolucionVenta)

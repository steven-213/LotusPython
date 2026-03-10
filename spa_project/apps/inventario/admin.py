from django.contrib import admin

from apps.inventario.models import Compra, DetalleCompra, DevolucionCompra, Producto, Proveedor

admin.site.register(Proveedor)
admin.site.register(Producto)
admin.site.register(Compra)
admin.site.register(DetalleCompra)
admin.site.register(DevolucionCompra)

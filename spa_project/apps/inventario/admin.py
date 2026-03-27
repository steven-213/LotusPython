from django.contrib import admin

from apps.inventario.models import Compra, DetalleCompra, DevolucionCompra, Inventario, Producto, Proveedor


@admin.register(Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
    list_display = ("nombre", "empresa", "telefono", "correo", "pais")
    list_filter = ("pais",)
    search_fields = ("nombre", "empresa", "correo", "nit")


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "proveedor", "stock_actual", "precio_compra", "precio_venta", "iva")
    list_filter = ("proveedor", "precio_venta", "activo")
    search_fields = ("nombre", "descripcion")
    readonly_fields = ("stock_actual",)
    fieldsets = (
        ("Informacion del Producto", {"fields": ("nombre", "descripcion", "imagen")}),
        ("Proveedor", {"fields": ("proveedor",)}),
        ("Precios", {"fields": ("precio_compra", "precio_venta", "iva", "margen_ganancia")}),
        ("Stock", {"fields": ("stock_actual",)}),
        ("Estado", {"fields": ("activo",)}),
    )

    @admin.display(description="Stock")
    def stock_actual(self, obj):
        return obj.stock


@admin.register(Inventario)
class InventarioAdmin(admin.ModelAdmin):
    list_display = ("producto", "lote", "stock", "precio_venta", "fecha_ingreso")
    list_filter = ("fecha_ingreso",)
    search_fields = ("producto__nombre", "lote")


@admin.register(Compra)
class CompraAdmin(admin.ModelAdmin):
    list_display = ("id", "proveedor", "numero_factura", "total", "fecha")
    list_filter = ("fecha", "proveedor")
    search_fields = ("numero_factura", "proveedor__nombre")
    readonly_fields = ("fecha",)


@admin.register(DetalleCompra)
class DetalleCompraAdmin(admin.ModelAdmin):
    list_display = ("compra", "producto", "cantidad", "precio_compra", "lote")
    list_filter = ("compra", "producto")
    search_fields = ("compra__numero_factura", "producto__nombre", "lote")


@admin.register(DevolucionCompra)
class DevolucionCompraAdmin(admin.ModelAdmin):
    list_display = ("compra", "producto", "cantidad", "estado", "fecha")
    list_filter = ("fecha", "estado")
    search_fields = ("compra__numero_factura", "producto__nombre", "motivo")

from django.contrib import admin

from apps.inventario.models import Compra, DetalleCompra, DevolucionCompra, Producto, Proveedor


@admin.register(Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
    list_display = ("nombre", "empresa", "telefono", "correo", "pais")
    list_filter = ("pais",)
    search_fields = ("nombre", "empresa", "correo", "nit")
    fieldsets = (
        ("Información General", {"fields": ("nombre", "empresa", "nit")}),
        ("Contacto", {"fields": ("telefono", "correo", "direccion")}),
        ("Ubicación", {"fields": ("pais",)}),
    )


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "proveedor", "stock", "precio_compra", "precio_venta", "iva")
    list_filter = ("proveedor", "precio_venta")
    search_fields = ("nombre", "descripcion")
    fieldsets = (
        ("Información del Producto", {"fields": ("nombre", "descripcion", "imagen")}),
        ("Proveedor", {"fields": ("proveedor",)}),
        ("Precios", {"fields": ("precio_compra", "precio_venta", "iva")}),
        ("Stock", {"fields": ("stock",)}),
    )
    readonly_fields = ("precio_venta",)


@admin.register(Compra)
class CompraAdmin(admin.ModelAdmin):
    list_display = ("id", "proveedor", "numero_factura", "total", "fecha")
    list_filter = ("fecha", "proveedor")
    search_fields = ("numero_factura", "proveedor__nombre")
    readonly_fields = ("fecha",)
    fieldsets = (
        ("Información de la Compra", {"fields": ("proveedor", "numero_factura", "fecha")}),
        ("Total", {"fields": ("total",)}),
    )


class DetalleCompraInline(admin.TabularInline):
    model = DetalleCompra
    extra = 0
    readonly_fields = ("producto",)


@admin.register(DetalleCompra)
class DetalleCompraAdmin(admin.ModelAdmin):
    list_display = ("compra", "producto", "cantidad", "precio_compra")
    list_filter = ("compra", "producto")
    search_fields = ("compra__numero_factura", "producto__nombre")
    readonly_fields = ("compra", "producto")


@admin.register(DevolucionCompra)
class DevolucionCompraAdmin(admin.ModelAdmin):
    list_display = ("compra", "producto", "cantidad", "motivo", "fecha")
    list_filter = ("fecha", "compra__proveedor")
    search_fields = ("compra__numero_factura", "producto__nombre", "motivo")
    readonly_fields = ("fecha",)
    fieldsets = (
        ("Información de la Devolución", {"fields": ("compra", "producto", "cantidad", "fecha")}),
        ("Motivo", {"fields": ("motivo",)}),
    )

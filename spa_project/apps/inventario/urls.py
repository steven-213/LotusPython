from django.urls import path

from apps.inventario.views.compra_views import (
    compra_lista,
    compra_nueva,
    finalizar_compra
)
from apps.inventario.views.producto_views import (
    producto_comprar,
    producto_detalle,
    producto_editar,
    producto_eliminar,
    producto_lista,
    producto_nuevo,
    productos_publicos,
)
from apps.inventario.views.proveedor_views import proveedor_lista, proveedor_nuevo

app_name = "inventario"

urlpatterns = [
    path("catalogo/", productos_publicos, name="productos_publicos"),
    path("catalogo/<int:producto_id>/comprar/", producto_comprar, name="producto_comprar"),
    path("productos/", producto_lista, name="producto_lista"),
    path("productos/nuevo/", producto_nuevo, name="producto_nuevo"),
    path("productos/<int:producto_id>/editar/", producto_editar, name="producto_editar"),
    path("productos/<int:producto_id>/eliminar/", producto_eliminar, name="producto_eliminar"),
    path("productos/<int:producto_id>/", producto_detalle, name="producto_detalle"),
    path("compras/", compra_lista, name="compra_lista"),
    path("compras/nueva/", compra_nueva, name="compra_nueva"),
    path("compras/finalizar/", finalizar_compra, name="finalizar_compra"),
    path("proveedores/", proveedor_lista, name="proveedor_lista"),
    path("proveedores/nuevo/", proveedor_nuevo, name="proveedor_nuevo"),
]

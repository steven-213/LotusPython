from django.urls import path

from apps.inventario.views.compra_views import (
    compra_detalle,
    compra_editar,
    compra_eliminar,
    compra_lista,
    compra_nueva,
    devolucion_detalle,
    devolucion_eliminar,
    devolucion_lista,
    devolucion_nueva,
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
from apps.inventario.views.proveedor_views import (
    proveedor_detalle,
    proveedor_editar,
    proveedor_eliminar,
    proveedor_lista,
    proveedor_nuevo,
)

app_name = "inventario"

urlpatterns = [
    # Productos
    path("catalogo/", productos_publicos, name="productos_publicos"),
    path("catalogo/<int:producto_id>/comprar/", producto_comprar, name="producto_comprar"),
    path("productos/", producto_lista, name="producto_lista"),
    path("productos/nuevo/", producto_nuevo, name="producto_nuevo"),
    path("productos/<int:producto_id>/editar/", producto_editar, name="producto_editar"),
    path("productos/<int:producto_id>/eliminar/", producto_eliminar, name="producto_eliminar"),
    path("productos/<int:producto_id>/", producto_detalle, name="producto_detalle"),
    
    # Compras
    path("compras/", compra_lista, name="compra_lista"),
    path("compras/nueva/", compra_nueva, name="compra_nueva"),
    path("compras/<int:compra_id>/editar/", compra_editar, name="compra_editar"),
    path("compras/<int:compra_id>/eliminar/", compra_eliminar, name="compra_eliminar"),
    path("compras/<int:compra_id>/", compra_detalle, name="compra_detalle"),
    
    # Proveedores
    path("proveedores/", proveedor_lista, name="proveedor_lista"),
    path("proveedores/nuevo/", proveedor_nuevo, name="proveedor_nuevo"),
    path("proveedores/<int:proveedor_id>/editar/", proveedor_editar, name="proveedor_editar"),
    path("proveedores/<int:proveedor_id>/eliminar/", proveedor_eliminar, name="proveedor_eliminar"),
    path("proveedores/<int:proveedor_id>/", proveedor_detalle, name="proveedor_detalle"),
    
    # Devoluciones
    path("devoluciones/", devolucion_lista, name="devolucion_lista"),
    path("devoluciones/nueva/", devolucion_nueva, name="devolucion_nueva"),
    path("devoluciones/<int:devolucion_id>/eliminar/", devolucion_eliminar, name="devolucion_eliminar"),
    path("devoluciones/<int:devolucion_id>/", devolucion_detalle, name="devolucion_detalle"),
]

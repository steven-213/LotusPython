from django.urls import path

from apps.ventas.views.api_views import api_resumen, api_ventas
from apps.ventas.views.devolucion_views import (
    aprobar_devolucion_telegram,
    rechazar_devolucion_telegram,
    solicitar_devolucion,
)
from apps.ventas.views.venta_views import (
    confirmar_compra_telegram,
    rechazar_compra_telegram,
    venta_detalle,
    venta_lista,
    venta_nueva,
    venta_validaciones,
    cancelar_compra,
)

app_name = "ventas"

urlpatterns = [
    path("", venta_lista, name="venta_lista"),
    path("listado/", venta_lista, name="venta_listado"),
    path("nueva/", venta_nueva, name="venta_nueva"),
    path("<int:venta_id>/", venta_detalle, name="venta_detalle"),
    path("<int:venta_id>/validaciones/", venta_validaciones, name="venta_validaciones"),
    path(
        "devoluciones/solicitar/<int:detalle_id>/",
        solicitar_devolucion,
        name="solicitar_devolucion",
    ),
    path("telegram/confirm/<int:validacion_id>/", confirmar_compra_telegram, name="telegram_confirm"),
    path("telegram/reject/<int:validacion_id>/", rechazar_compra_telegram, name="telegram_reject"),
    path(
        "telegram/returns/<int:solicitud_id>/approve/",
        aprobar_devolucion_telegram,
        name="telegram_return_approve",
    ),
    path(
        "telegram/returns/<int:solicitud_id>/reject/",
        rechazar_devolucion_telegram,
        name="telegram_return_reject",
    ),
    path("api/ventas/", api_ventas, name="api_ventas"),
    path("api/resumen/", api_resumen, name="api_resumen"),
    path('cancelar-compra/<int:validacion_id>/', cancelar_compra, name='cancelar_compra'),
]

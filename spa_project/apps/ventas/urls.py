from django.urls import path

from apps.ventas.views.api_views import api_resumen, api_ventas
from apps.ventas.views.venta_views import (
    confirmar_compra_telegram,
    rechazar_compra_telegram,
    venta_detalle,
    venta_lista,
    venta_nueva,
    venta_validaciones,
)

app_name = "ventas"

urlpatterns = [
    path("", venta_lista, name="venta_lista"),
    path("nueva/", venta_nueva, name="venta_nueva"),
    path("<int:venta_id>/", venta_detalle, name="venta_detalle"),
    path("<int:venta_id>/validaciones/", venta_validaciones, name="venta_validaciones"),
    path("telegram/confirm/<int:validacion_id>/", confirmar_compra_telegram, name="telegram_confirm"),
    path("telegram/reject/<int:validacion_id>/", rechazar_compra_telegram, name="telegram_reject"),
    path("api/ventas/", api_ventas, name="api_ventas"),
    path("api/resumen/", api_resumen, name="api_resumen"),
]

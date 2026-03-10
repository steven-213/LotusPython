from django.urls import path

from apps.ventas.views.api_views import api_resumen, api_ventas
from apps.ventas.views.venta_views import (
    telegram_confirm_purchase,
    telegram_reject_purchase,
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
    path("telegram/confirm/<int:validacion_id>/", telegram_confirm_purchase, name="telegram_confirm"),
    path("telegram/reject/<int:validacion_id>/", telegram_reject_purchase, name="telegram_reject"),
    path("api/ventas/", api_ventas, name="api_ventas"),
    path("api/resumen/", api_resumen, name="api_resumen"),
]

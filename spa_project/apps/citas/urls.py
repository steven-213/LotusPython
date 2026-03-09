from django.urls import path

from apps.citas.views.api_views import api_eventos
from apps.citas.views.cita_views import agenda, calendario, cita_editar, cita_nueva
from apps.citas.views.servicio_views import (
    servicio_editar,
    servicio_eliminar,
    servicio_lista,
    servicio_nuevo,
    servicios_publicos,
)

app_name = "citas"

urlpatterns = [
    path("calendario/", calendario, name="calendario"),
    path("agenda/", agenda, name="agenda"),
    path("nueva/", cita_nueva, name="cita_nueva"),
    path("<int:cita_id>/editar/", cita_editar, name="cita_editar"),
    path("catalogo/", servicios_publicos, name="servicios_publicos"),
    path("servicios/", servicio_lista, name="servicio_lista"),
    path("servicios/nuevo/", servicio_nuevo, name="servicio_nuevo"),
    path("servicios/<int:servicio_id>/editar/", servicio_editar, name="servicio_editar"),
    path("servicios/<int:servicio_id>/eliminar/", servicio_eliminar, name="servicio_eliminar"),
    path("api/eventos/", api_eventos, name="api_eventos"),
]

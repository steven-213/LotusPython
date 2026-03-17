from django.urls import path

from apps.citas.views.api_views import api_eventos
from apps.citas.views.cita_views import agenda, calendario, reserva_editar, reserva_nueva
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
    path("nueva/", reserva_nueva, name="reserva_nueva"),
    path("<int:reserva_id>/editar/", reserva_editar, name="reserva_editar"),
    path("catalogo/", servicios_publicos, name="servicios_publicos"),
    path("servicios/", servicio_lista, name="servicio_lista"),
    path("servicios/nuevo/", servicio_nuevo, name="servicio_nuevo"),
    path("servicios/<int:servicio_id>/editar/", servicio_editar, name="servicio_editar"),
    path("servicios/<int:servicio_id>/eliminar/", servicio_eliminar, name="servicio_eliminar"),
    path("api/eventos/", api_eventos, name="api_eventos"),
]

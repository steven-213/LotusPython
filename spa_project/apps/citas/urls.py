from django.urls import path

from apps.citas.views.api_views import api_eventos
from apps.citas.views.cita_views import (
    agenda,
    calendario,
    comprobante_pago_pdf,
    reserva_cancelar,
    reserva_confirmada,
    reserva_confirmar,
    reserva_detalle,
    reserva_editar,
    reserva_finalizar,
    reserva_iniciar,
    reserva_no_asistio,
    reserva_nueva,
    reserva_registrar_pago,
)
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
    path("reserva-confirmada/", reserva_confirmada, name="reserva_confirmada"),
    path("catalogo/", servicios_publicos, name="servicios_publicos"),
    path("servicios/", servicio_lista, name="servicio_lista"),
    path("servicios/nuevo/", servicio_nuevo, name="servicio_nuevo"),
    path("servicios/<int:servicio_id>/editar/", servicio_editar, name="servicio_editar"),
    path("servicios/<int:servicio_id>/eliminar/", servicio_eliminar, name="servicio_eliminar"),
    path("<int:reserva_id>/detalle/", reserva_detalle, name="reserva_detalle"),
    path("<int:reserva_id>/editar/", reserva_editar, name="reserva_editar"),
    path("<int:reserva_id>/cancelar/", reserva_cancelar, name="reserva_cancelar"),
    path("<int:reserva_id>/confirmar/", reserva_confirmar, name="reserva_confirmar"),
    path("<int:reserva_id>/iniciar/", reserva_iniciar, name="reserva_iniciar"),
    path("<int:reserva_id>/finalizar/", reserva_finalizar, name="reserva_finalizar"),
    path("<int:reserva_id>/no-asistio/", reserva_no_asistio, name="reserva_no_asistio"),
    path("<int:reserva_id>/pago/", reserva_registrar_pago, name="reserva_registrar_pago"),
    path("pagos/<int:pago_id>/comprobante/", comprobante_pago_pdf, name="comprobante_pago_pdf"),
    path("api/eventos/", api_eventos, name="api_eventos"),
]

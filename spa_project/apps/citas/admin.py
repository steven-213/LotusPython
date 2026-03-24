from django.contrib import admin

from apps.citas.models import ClienteInvitado, PagoReserva, Profesional, Reserva, ReservaHistorialEstado, Servicio


@admin.register(ClienteInvitado)
class ClienteInvitadoAdmin(admin.ModelAdmin):
    list_display = ("documento", "nombre", "apellido", "correo", "created_at")
    search_fields = ("documento", "nombre", "apellido", "correo")


@admin.register(Profesional)
class ProfesionalAdmin(admin.ModelAdmin):
    list_display = ("nombre", "activo", "created_at")
    search_fields = ("nombre",)
    list_filter = ("activo",)


@admin.register(Servicio)
class ServicioAdmin(admin.ModelAdmin):
    list_display = ("nombre", "profesional", "duracion_minutos", "precio", "activo")
    search_fields = ("nombre", "profesional__nombre")
    list_filter = ("activo", "profesional")


@admin.register(Reserva)
class ReservaAdmin(admin.ModelAdmin):
    list_display = ("id", "cliente_nombre_completo", "servicio", "fecha_inicio", "estado", "origen_reserva")
    search_fields = (
        "cliente__nombre",
        "cliente__apellido",
        "cliente_invitado__nombre",
        "cliente_invitado__apellido",
        "servicio__nombre",
    )
    list_filter = ("estado", "origen_reserva", "servicio__profesional")


@admin.register(ReservaHistorialEstado)
class ReservaHistorialEstadoAdmin(admin.ModelAdmin):
    list_display = ("reserva", "estado_anterior", "estado_nuevo", "usuario_actor", "fecha")
    list_filter = ("estado_nuevo",)
    search_fields = (
        "reserva__cliente__nombre",
        "reserva__cliente_invitado__nombre",
        "reserva__servicio__nombre",
    )


@admin.register(PagoReserva)
class PagoReservaAdmin(admin.ModelAdmin):
    list_display = ("numero_comprobante", "reserva", "monto", "metodo_pago", "estado", "fecha_pago")
    list_filter = ("estado", "metodo_pago", "tipo")
    search_fields = (
        "numero_comprobante",
        "reserva__cliente__nombre",
        "reserva__cliente_invitado__nombre",
        "referencia",
    )

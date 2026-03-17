from django.contrib import admin

from apps.citas.models import Reserva, Servicio

admin.site.register(Servicio)
admin.site.register(Reserva)

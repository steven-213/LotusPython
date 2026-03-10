from django.contrib import admin

from apps.citas.models import Cita, Servicio

admin.site.register(Servicio)
admin.site.register(Cita)

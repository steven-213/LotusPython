from django.contrib import admin

from apps.sesiones.models import RecuperacionClave, RegistroPendiente, Usuario

admin.site.register(Usuario)
admin.site.register(RegistroPendiente)
admin.site.register(RecuperacionClave)

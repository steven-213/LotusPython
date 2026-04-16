from django.contrib import admin

from apps.membresias.models import MembresiaUsuario, PlanMembresia


@admin.register(PlanMembresia)
class PlanMembresiaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "precio", "duracion_dias", "destacado", "activo", "orden")
    list_filter = ("activo", "destacado")
    search_fields = ("nombre", "subtitulo", "descripcion")
    prepopulated_fields = {"slug": ("nombre",)}


@admin.register(MembresiaUsuario)
class MembresiaUsuarioAdmin(admin.ModelAdmin):
    list_display = ("usuario", "plan", "estado", "fecha_inicio", "fecha_fin", "origen")
    list_filter = ("estado", "origen", "plan")
    search_fields = (
        "usuario__nombre",
        "usuario__apellido",
        "=usuario__documento",
        "plan__nombre",
    )
    raw_id_fields = ("usuario", "plan", "creada_por")

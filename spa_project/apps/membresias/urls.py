from django.urls import path

from apps.membresias.views.dashboard_views import (
    dashboard,
    miembro_asignar,
    miembro_cancelar,
    miembro_lista,
    plan_editar,
    plan_lista,
    plan_nuevo,
    plan_toggle,
)
from apps.membresias.views.public_views import activar_membresia, membresias_publicas

app_name = "membresias"

urlpatterns = [
    path("", membresias_publicas, name="membresias"),
    path("activar/<int:plan_id>/", activar_membresia, name="activar_membresia"),
    path("dashboard/", dashboard, name="dashboard"),
    path("dashboard/planes/", plan_lista, name="plan_lista"),
    path("dashboard/planes/nuevo/", plan_nuevo, name="plan_nuevo"),
    path("dashboard/planes/<int:plan_id>/editar/", plan_editar, name="plan_editar"),
    path("dashboard/planes/<int:plan_id>/estado/", plan_toggle, name="plan_toggle"),
    path("dashboard/miembros/", miembro_lista, name="miembro_lista"),
    path("dashboard/miembros/asignar/", miembro_asignar, name="miembro_asignar"),
    path("dashboard/miembros/<int:membresia_id>/cancelar/", miembro_cancelar, name="miembro_cancelar"),
]


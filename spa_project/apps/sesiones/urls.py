from django.urls import path

from apps.sesiones.views.auth_views import (
    admin_dashboard,
    conocenos,
    index,
    login_view,
    logout_view,
    recuperar_contrasena,
    registro,
    restablecer_contrasena,
)
from apps.sesiones.views.profile_views import perfil, perfil_editar, perfil_eliminar
from apps.sesiones.views.usuario_admin_views import (
    usuario_detalle,
    usuario_editar,
    usuario_eliminar,
    usuario_lista,
    usuario_nuevo,
)

app_name = "sesiones"

urlpatterns = [
    path("", index, name="home"),
    path("conocenos/", conocenos, name="conocenos"),
    path("login/", login_view, name="login"),
    path("recuperar-contrasena/", recuperar_contrasena, name="recuperar_contrasena"),
    path("restablecer-contrasena/<path:token>/", restablecer_contrasena, name="restablecer_contrasena"),
    path("logout/", logout_view, name="logout"),
    path("registro/", registro, name="registro"),
    path("perfil/", perfil, name="perfil"),
    path("perfil/editar/", perfil_editar, name="perfil_editar"),
    path("perfil/eliminar/", perfil_eliminar, name="perfil_eliminar"),
    path("admin-panel/", admin_dashboard, name="admin_dashboard"),
    path("admin-panel/usuarios/", usuario_lista, name="usuario_lista"),
    path("admin-panel/usuarios/nuevo/", usuario_nuevo, name="usuario_nuevo"),
    path("admin-panel/usuarios/<int:usuario_id>/", usuario_detalle, name="usuario_detalle"),
    path("admin-panel/usuarios/<int:usuario_id>/editar/", usuario_editar, name="usuario_editar"),
    path("admin-panel/usuarios/<int:usuario_id>/eliminar/", usuario_eliminar, name="usuario_eliminar"),
]

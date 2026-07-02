from django.urls import path

from apps.sesiones.views.auth_views import (
    admin_dashboard,
    conocenos,
    index,
    login_view,
    logout_view,
    registro,
    solicitar_reset_contrasena,
    confirmar_reset_contrasena,
)
from apps.sesiones.views.profile_views import perfil
from apps.sesiones.views.admin_users_views import (
    usuarios_lista,
    usuarios_nuevo,
    usuarios_detalle,
    usuarios_editar,
    usuarios_eliminar,
)

app_name = "sesiones"

urlpatterns = [
    path("", index, name="home"),
    path("conocenos/", conocenos, name="conocenos"),
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("registro/", registro, name="registro"),
    path("perfil/", perfil, name="perfil"),
    path("admin-panel/", admin_dashboard, name="admin_dashboard"),
    path("olvide-contrasena/", solicitar_reset_contrasena, name="solicitar_reset_contrasena"),
    path("resetear-contrasena/<str:token>/", confirmar_reset_contrasena, name="confirmar_reset_contrasena"),
    # Usuarios Admin
    path("usuarios/", usuarios_lista, name="usuarios_lista"),
    path("usuarios/nuevo/", usuarios_nuevo, name="usuarios_nuevo"),
    path("usuarios/<int:usuario_id>/", usuarios_detalle, name="usuarios_detalle"),
    path("usuarios/<int:usuario_id>/editar/", usuarios_editar, name="usuarios_editar"),
    path("usuarios/<int:usuario_id>/eliminar/", usuarios_eliminar, name="usuarios_eliminar"),
]

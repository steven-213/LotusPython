from django.urls import path

from apps.sesiones.views.auth_views import (
    admin_dashboard,
    conocenos,
    index,
    login_view,
    logout_view,
    registro,
)
from apps.sesiones.views.profile_views import perfil

app_name = "sesiones"

urlpatterns = [
    path("", index, name="home"),
    path("conocenos/", conocenos, name="conocenos"),
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("registro/", registro, name="registro"),
    path("perfil/", perfil, name="perfil"),
    path("admin-panel/", admin_dashboard, name="admin_dashboard"),
]

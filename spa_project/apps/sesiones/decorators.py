from functools import wraps
from urllib.parse import urlencode

from django.shortcuts import redirect
from django.urls import reverse

from apps.sesiones.models import Usuario
from apps.sesiones.session_utils import asegurar_vencimiento_sesion


def _resolver_usuario_sesion(request):
    if not getattr(request, "_manual_session_checked", False) and not asegurar_vencimiento_sesion(request):
        return None
    if not request.session.get("usuario_id"):
        return None

    usuario_id = request.session.get("usuario_id")

    usuario = Usuario.objects.filter(id=usuario_id).only("id", "rol").first()
    if not usuario:
        request.session.flush()
        return None

    if request.session.get("usuario_rol") != usuario.rol:
        request.session["usuario_rol"] = usuario.rol
        request.session.modified = True

    return usuario


def _redirigir_login(request):
    login_url = reverse("sesiones:login")
    next_url = request.get_full_path()
    params = {}
    if next_url and next_url != login_url:
        params["next"] = next_url
    if getattr(request, "manual_session_expired", False):
        params["reason"] = "session_expired"
    if params:
        return redirect(f"{login_url}?{urlencode(params)}")
    return redirect(login_url)


def login_required_session(view_func):
    # Protege vistas que requieren sesion activa basada en la sesion manual del proyecto.
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not _resolver_usuario_sesion(request):
            return _redirigir_login(request)
        return view_func(request, *args, **kwargs)

    return wrapper


def admin_required_session(view_func):
    # Protege vistas solo para usuarios con rol admin.
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        usuario = _resolver_usuario_sesion(request)
        if not usuario:
            return _redirigir_login(request)
        if usuario.rol != Usuario.ROL_ADMIN:
            return redirect("sesiones:perfil")
        return view_func(request, *args, **kwargs)

    return wrapper

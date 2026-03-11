from functools import wraps

from django.shortcuts import redirect


def login_required_session(view_func):
    # Protege vistas que requieren sesion activa basada en la sesion manual del proyecto.
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if "usuario_id" not in request.session:
            return redirect("sesiones:login")
        return view_func(request, *args, **kwargs)

    return wrapper


def admin_required_session(view_func):
    # Protege vistas solo para usuarios con rol admin.
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if "usuario_id" not in request.session:
            return redirect("sesiones:login")
        if request.session.get("usuario_rol") != "admin":
            return redirect("sesiones:perfil")
        return view_func(request, *args, **kwargs)

    return wrapper

from django.contrib import messages
from django.shortcuts import redirect, render

from apps.sesiones.decorators import admin_required_session
from apps.sesiones.models import Usuario


def index(request):
    usuario = None
    usuario_id = request.session.get("usuario_id")
    if usuario_id:
        usuario = Usuario.objects.filter(id=usuario_id).first()
    return render(request, "index.html", {"usuario": usuario})


def conocenos(request):
    return render(request, "conocenos.html")


def login_view(request):
    next_url = request.GET.get("next") or request.POST.get("next")
    reason = request.GET.get("reason")
    if request.method == "GET" and reason == "agendar":
        messages.info(request, "Debes iniciar sesion para agendar una cita.")
    elif request.method == "GET" and reason == "comprar":
        messages.info(request, "Debes iniciar sesion para continuar con la compra.")

    if request.method == "POST":
        documento = request.POST.get("documento")
        clave = request.POST.get("clave")
        usuario = Usuario.objects.filter(documento=documento, clave=clave).first()
        if usuario:
            request.session["usuario_id"] = usuario.id
            request.session["usuario_rol"] = usuario.rol
            if next_url:
                return redirect(next_url)
            if usuario.rol == Usuario.ROL_ADMIN:
                return redirect("sesiones:admin_dashboard")
            return redirect("citas:calendario")
        messages.error(request, "Documento o contrasena incorrectos.")
    return render(request, "login.html", {"next": next_url})


def registro(request):
    if request.method == "POST":
        Usuario.objects.create(
            documento=request.POST.get("documento"),
            nombre=request.POST.get("nombre"),
            apellido=request.POST.get("apellido"),
            correo=request.POST.get("correo"),
            fecha_nacimiento=request.POST.get("fecha_nacimiento") or request.POST.get("fechaNacimiento"),
            clave=request.POST.get("clave"),
            rol=request.POST.get("rol", Usuario.ROL_CLIENTE),
        )
        messages.success(request, "Usuario registrado correctamente.")
        return redirect("sesiones:login")
    return render(request, "registro.html")


def logout_view(request):
    request.session.flush()
    return redirect("sesiones:login")


@admin_required_session
def admin_dashboard(request):
    return render(request, "administrador/dashboard.html")

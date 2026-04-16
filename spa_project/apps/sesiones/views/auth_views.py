from django.contrib import messages
from django.shortcuts import redirect, render

from apps.common.seo import apply_public_page_cache_headers, serialize_structured_data
from apps.sesiones.decorators import admin_required_session
from apps.sesiones.models import Usuario


def index(request):
    structured_data = {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": "Inicio | Lotus Dream Spa",
        "description": (
            "Explora servicios de spa, agenda tu cita y descubre productos "
            "para continuar tu ritual de bienestar en casa."
        ),
    }
    response = render(
        request,
        "index.html",
        {
            "meta_title": "Inicio | Lotus Dream Spa",
            "meta_description": (
                "Reserva servicios de spa, conoce Lotus Dream Spa y descubre "
                "productos de bienestar y cuidado personal."
            ),
            "structured_data_json": serialize_structured_data(structured_data),
        },
    )
    return apply_public_page_cache_headers(response)


def conocenos(request):
    response = render(
        request,
        "conocenos.html",
        {
            "meta_title": "Conócenos | Lotus Dream Spa",
            "meta_description": (
                "Conoce la esencia de Lotus Dream Spa, nuestro enfoque en "
                "bienestar, cuidado personalizado y atención profesional."
            ),
        },
    )
    return apply_public_page_cache_headers(response)


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
        documento = request.POST.get("documento")
        correo = (request.POST.get("correo") or "").strip()
        form_data = {
            "documento": documento,
            "nombre": request.POST.get("nombre", ""),
            "apellido": request.POST.get("apellido", ""),
            "correo": correo,
            "fecha_nacimiento": request.POST.get("fecha_nacimiento") or request.POST.get("fechaNacimiento", ""),
        }

        if Usuario.objects.filter(documento=documento).exists():
            messages.error(request, "Ya existe una cuenta registrada con ese documento.")
            return render(
                request,
                "registro.html",
                {
                    "form_data": form_data,
                    "duplicate_documento": True,
                },
            )

        if correo and Usuario.objects.filter(correo__iexact=correo).exists():
            messages.error(request, "Ya existe una cuenta registrada con ese correo.")
            return render(
                request,
                "registro.html",
                {
                    "form_data": form_data,
                    "duplicate_correo": True,
                },
            )

        Usuario.objects.create(
            documento=documento,
            nombre=form_data["nombre"],
            apellido=form_data["apellido"],
            correo=form_data["correo"],
            fecha_nacimiento=form_data["fecha_nacimiento"],
            clave=request.POST.get("clave"),
            rol=request.POST.get("rol", Usuario.ROL_CLIENTE),
        )
        messages.success(request, "Usuario registrado correctamente.")
        return redirect("sesiones:login")
    return render(request, "registro.html", {"form_data": {}})


def logout_view(request):
    request.session.flush()
    return redirect("sesiones:login")


@admin_required_session
def admin_dashboard(request):
    return render(request, "administrador/dashboard.html")

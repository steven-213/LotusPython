from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse

from apps.common.seo import apply_public_page_cache_headers, serialize_structured_data
from apps.ventas.models import SolicitudDevolucionVenta
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
            request.session["usuario_nombre"] = f"{usuario.nombre} {usuario.apellido}".strip()
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
    pending_client_returns = SolicitudDevolucionVenta.objects.filter(
        estado=SolicitudDevolucionVenta.ESTADO_PENDIENTE
    ).count()

    def safe_reverse(view_name):
        try:
            return reverse(view_name)
        except NoReverseMatch:
            return ""

    module_cards = [
        {
            "title": "Inventario",
            "icon": "bi-box-seam",
            "copy": "Gestiona productos, compras, proveedores y devoluciones desde un solo espacio.",
            "url": safe_reverse("inventario:dashboard"),
            "links": [
                {"label": "Productos", "url": safe_reverse("inventario:producto_lista")},
                {"label": "Compras", "url": safe_reverse("inventario:compra_lista")},
                {"label": "Proveedores", "url": safe_reverse("inventario:proveedor_lista")},
            ],
        },
        {
            "title": "Ventas",
            "icon": "bi-receipt",
            "copy": "Revisa ventas, validaciones y seguimiento comercial del día.",
            "url": safe_reverse("ventas:venta_lista"),
            "links": [
                {"label": "Resumen", "url": safe_reverse("ventas:venta_lista")},
                {"label": "Nueva venta", "url": safe_reverse("ventas:venta_nueva")},
            ],
        },
        {
            "title": "Citas",
            "icon": "bi-calendar-event",
            "copy": "Consulta el calendario y entra rápido a reservas y servicios.",
            "url": safe_reverse("citas:calendario"),
            "links": [
                {"label": "Calendario", "url": safe_reverse("citas:calendario")},
                {"label": "Servicios", "url": safe_reverse("citas:servicio_lista")},
            ],
        },
        {
            "title": "Devoluciones",
            "icon": "bi-arrow-return-left",
            "copy": "Centraliza devoluciones de compra y solicitudes hechas por clientes.",
            "url": safe_reverse("inventario:devolucion_lista"),
            "links": [
                {"label": "Historial", "url": safe_reverse("inventario:devolucion_lista")},
                {"label": "Nueva devolución", "url": safe_reverse("inventario:devolucion_nueva")},
            ],
            "badge": f"{pending_client_returns} pendiente(s)" if pending_client_returns else "",
        },
    ]
    module_cards = [
        {
            **card,
            "links": [link for link in card["links"] if link["url"]],
        }
        for card in module_cards
        if card["url"]
    ]

    return render(
        request,
        "administrador/dashboard.html",
        {
            "module_cards": module_cards,
            "pending_client_returns": pending_client_returns,
        },
    )

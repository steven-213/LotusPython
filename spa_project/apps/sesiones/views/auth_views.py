from django.contrib import messages
from django.conf import settings
from django.core import signing
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse

from apps.common.seo import apply_public_page_cache_headers, serialize_structured_data
from apps.common.validation import (
    validate_birth_date,
    validate_digits_string,
    validate_email,
    validate_name,
    validate_password,
)
from apps.ventas.models import SolicitudDevolucionVenta
from apps.sesiones.decorators import admin_required_session
from apps.sesiones.models import Usuario


PASSWORD_RESET_SALT = "sesiones-password-reset"
PASSWORD_RESET_MAX_AGE = 60 * 60


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
        if usuario and usuario.activo:
            request.session["usuario_id"] = usuario.id
            request.session["usuario_rol"] = usuario.rol
            request.session["usuario_nombre"] = f"{usuario.nombre} {usuario.apellido}".strip()
            if next_url:
                return redirect(next_url)
            if usuario.rol == Usuario.ROL_ADMIN:
                return redirect("sesiones:admin_dashboard")
            return redirect("sesiones:perfil")
        messages.error(request, "Documento o contrasena incorrectos, o la cuenta esta inactiva.")
    return render(request, "login.html", {"next": next_url})


def recuperar_contrasena(request):
    if request.method == "POST":
        correo = (request.POST.get("correo") or "").strip().lower()
        try:
            correo = validate_email(correo)
        except ValueError as exc:
            messages.error(request, str(exc))
            return render(request, "recuperar_contrasena.html", {"correo": correo})

        usuario = Usuario.objects.filter(correo__iexact=correo).first()
        if not usuario:
            messages.error(request, "No existe una cuenta registrada con ese correo.")
            return render(request, "recuperar_contrasena.html", {"correo": correo})

        token = signing.dumps(
            {"usuario_id": usuario.id, "clave_actual": usuario.clave},
            salt=PASSWORD_RESET_SALT,
        )
        reset_url = request.build_absolute_uri(
            reverse("sesiones:restablecer_contrasena", kwargs={"token": token})
        )
        send_mail(
            "Recupera tu contrasena en Lotus Dream Spa",
            f"Usa este enlace para crear una nueva contrasena: {reset_url}",
            getattr(settings, "DEFAULT_FROM_EMAIL", None),
            [usuario.correo],
            fail_silently=False,
        )
        messages.success(request, "Te enviamos un enlace de recuperacion al correo registrado.")
        return redirect("sesiones:login")
    return render(request, "recuperar_contrasena.html", {})


def restablecer_contrasena(request, token):
    try:
        payload = signing.loads(
            token,
            salt=PASSWORD_RESET_SALT,
            max_age=PASSWORD_RESET_MAX_AGE,
        )
        usuario = Usuario.objects.get(id=payload["usuario_id"])
        if payload.get("clave_actual") != usuario.clave:
            raise signing.BadSignature("Token usado")
    except (Usuario.DoesNotExist, signing.BadSignature, signing.SignatureExpired):
        messages.error(request, "El enlace de recuperacion no es valido o ya expiro.")
        return redirect("sesiones:recuperar_contrasena")

    if request.method == "POST":
        clave = request.POST.get("clave") or ""
        confirmacion = request.POST.get("confirmacion_clave") or ""
        try:
            clave_limpia = validate_password(clave)
            if clave_limpia != confirmacion.strip():
                raise ValueError("La confirmacion de la contrasena no coincide.")
        except ValueError as exc:
            messages.error(request, str(exc))
            return render(request, "restablecer_contrasena.html", {"token": token})

        usuario.clave = clave_limpia
        usuario.save(update_fields=["clave"])
        messages.success(request, "Tu contrasena fue actualizada. Inicia sesion con la nueva clave.")
        return redirect("sesiones:login")

    return render(request, "restablecer_contrasena.html", {"token": token})


def _render_registro(request, *, form_data, duplicate_documento=False, duplicate_correo=False):
    return render(
        request,
        "registro.html",
        {
            "form_data": form_data,
            "duplicate_documento": duplicate_documento,
            "duplicate_correo": duplicate_correo,
        },
    )


def registro(request):
    if request.method == "POST":
        documento = (request.POST.get("documento") or "").strip()
        correo = (request.POST.get("correo") or "").strip()
        form_data = {
            "documento": documento,
            "nombre": request.POST.get("nombre", ""),
            "apellido": request.POST.get("apellido", ""),
            "correo": correo,
            "fecha_nacimiento": request.POST.get("fecha_nacimiento") or request.POST.get("fechaNacimiento", ""),
        }
        clave = request.POST.get("clave") or ""
        confirmacion_clave = request.POST.get("confirmacion_clave", clave)
        rol = request.POST.get("rol", Usuario.ROL_CLIENTE)

        try:
            documento_limpio = validate_digits_string(
                documento,
                label="El documento",
                min_length=3,
                max_length=15,
            )
            nombre = validate_name(form_data["nombre"], label="El nombre")
            apellido = validate_name(form_data["apellido"], label="El apellido")
            correo_limpio = validate_email(correo)
            fecha_nacimiento = validate_birth_date(form_data["fecha_nacimiento"])
            clave_limpia = validate_password(clave)

            if confirmacion_clave == "":
                raise ValueError("Debes confirmar la contrasena.")
            if clave_limpia != str(confirmacion_clave).strip():
                raise ValueError("La confirmacion de la contrasena no coincide.")
            if rol not in {Usuario.ROL_ADMIN, Usuario.ROL_CLIENTE}:
                raise ValueError("El rol seleccionado no es valido.")
        except ValueError as exc:
            messages.error(request, str(exc))
            return _render_registro(request, form_data=form_data)

        if Usuario.objects.filter(documento=documento_limpio).exists():
            messages.error(request, "Ya existe una cuenta registrada con ese documento.")
            return _render_registro(request, form_data=form_data, duplicate_documento=True)

        if correo_limpio and Usuario.objects.filter(correo__iexact=correo_limpio).exists():
            messages.error(request, "Ya existe una cuenta registrada con ese correo.")
            return _render_registro(request, form_data=form_data, duplicate_correo=True)

        Usuario.objects.create(
            documento=int(documento_limpio),
            nombre=nombre,
            apellido=apellido,
            correo=correo_limpio,
            fecha_nacimiento=fecha_nacimiento,
            clave=clave_limpia,
            rol=rol,
        )
        messages.success(request, "Usuario registrado correctamente.")
        return redirect("sesiones:login")
    return _render_registro(request, form_data={})


def logout_view(request):
    request.session.flush()
    return redirect("sesiones:login")


@admin_required_session
def admin_dashboard(request):
    pending_client_returns = SolicitudDevolucionVenta.objects.filter(
        estado=SolicitudDevolucionVenta.ESTADO_PENDIENTE
    ).count()
    usuarios_total = Usuario.objects.count()

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
            "copy": "Consulta el dashboard y entra rapido a reservas y servicios.",
            "url": safe_reverse("citas:dashboard"),
            "links": [
                {"label": "Dashboard", "url": safe_reverse("citas:dashboard")},
                {"label": "Almanaque", "url": safe_reverse("citas:almanaque")},
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
        {
            "title": "Usuarios",
            "icon": "bi-people",
            "copy": "Administra clientes, administradores, estado de cuenta y datos de contacto.",
            "url": safe_reverse("sesiones:usuario_lista"),
            "links": [
                {"label": "Listado", "url": safe_reverse("sesiones:usuario_lista")},
                {"label": "Nuevo usuario", "url": safe_reverse("sesiones:usuario_nuevo")},
            ],
            "badge": f"{usuarios_total} usuario(s)",
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

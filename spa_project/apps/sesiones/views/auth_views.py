from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.common.seo import apply_public_page_cache_headers, serialize_structured_data
from apps.sesiones.decorators import admin_required_session
from apps.sesiones.models import RecuperacionClave, RegistroPendiente, Usuario
from apps.sesiones.security import (
    MailDeliveryError,
    check_usuario_password,
    generate_verification_code,
    get_code_expiration,
    hash_secret,
    normalize_email,
    secret_matches,
    send_password_reset_code_email,
    send_registration_code_email,
    set_usuario_password,
)
from apps.ventas.models import SolicitudDevolucionVenta


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
        clave = request.POST.get("clave") or ""
        usuario = Usuario.objects.filter(documento=documento).first()
        if usuario and check_usuario_password(usuario, clave):
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
    form_data = _build_registration_form_data(request)

    if request.method == "POST":
        invalid_context = _validate_registration_request(form_data, request.POST.get("clave") or "")
        if invalid_context:
            messages.error(request, invalid_context["message"])
            return render(request, "registro.html", invalid_context)

        verification_code = generate_verification_code()
        pending_registration = _save_pending_registration(
            form_data=form_data,
            raw_password=request.POST.get("clave") or "",
            verification_code=verification_code,
        )

        try:
            send_registration_code_email(form_data["correo"], verification_code)
        except MailDeliveryError:
            messages.error(
                request,
                "No fue posible enviar el codigo al correo indicado. Revisa la configuracion del correo e intenta de nuevo.",
            )
            return render(request, "registro.html", {"form_data": form_data})

        messages.success(
            request,
            f"Te enviamos un codigo de verificacion a {form_data['correo']}. Ingresa el codigo para completar el registro.",
        )
        return redirect("sesiones:registro_verificar", token=pending_registration.token)

    return render(request, "registro.html", {"form_data": form_data})


def registro_verificar(request, token):
    pending_registration = get_object_or_404(RegistroPendiente, token=token)

    if request.method == "POST":
        if request.POST.get("action") == "resend":
            return _resend_registration_code(request, pending_registration)

        verification_code = (request.POST.get("codigo") or "").strip()
        if not verification_code:
            messages.error(request, "Ingresa el codigo que recibiste por correo.")
        elif pending_registration.codigo_expira_en <= timezone.now():
            messages.error(request, "El codigo ya vencio. Solicita uno nuevo para continuar.")
        elif not secret_matches(verification_code, pending_registration.codigo):
            messages.error(request, "El codigo ingresado no es valido.")
        else:
            if Usuario.objects.filter(documento=pending_registration.documento).exists():
                messages.error(request, "Ya existe una cuenta registrada con ese documento.")
            elif Usuario.objects.filter(correo__iexact=pending_registration.correo).exists():
                messages.error(request, "Ya existe una cuenta registrada con ese correo.")
            else:
                Usuario.objects.create(
                    documento=pending_registration.documento,
                    nombre=pending_registration.nombre,
                    apellido=pending_registration.apellido,
                    correo=pending_registration.correo,
                    fecha_nacimiento=pending_registration.fecha_nacimiento,
                    clave=pending_registration.clave,
                    rol=Usuario.ROL_CLIENTE,
                )
                pending_registration.delete()
                messages.success(
                    request,
                    "Cuenta verificada y creada correctamente. Ya puedes iniciar sesion.",
                )
                return redirect("sesiones:login")

    return render(
        request,
        "registro_verificar.html",
        {
            "pending_registration": pending_registration,
            "expires_in_minutes": _minutes_until_expiration(pending_registration.codigo_expira_en),
        },
    )


def password_reset_request(request):
    form_data = {
        "documento": request.POST.get("documento", ""),
        "correo": normalize_email(request.POST.get("correo", "")),
    }

    if request.method == "POST":
        documento = form_data["documento"]
        correo = form_data["correo"]

        if not documento or not correo:
            messages.error(request, "Completa el documento y el correo para continuar.")
            return render(request, "password_reset_request.html", {"form_data": form_data})

        usuario = Usuario.objects.filter(documento=documento, correo__iexact=correo).first()
        if not usuario:
            messages.error(request, "No encontramos una cuenta con ese documento y correo.")
            return render(request, "password_reset_request.html", {"form_data": form_data})

        verification_code = generate_verification_code()
        password_reset = RecuperacionClave.objects.update_or_create(
            usuario=usuario,
            defaults={
                "correo": usuario.correo,
                "codigo": hash_secret(verification_code),
                "codigo_expira_en": get_code_expiration(),
            },
        )[0]

        try:
            send_password_reset_code_email(usuario.correo, verification_code)
        except MailDeliveryError:
            messages.error(
                request,
                "No fue posible enviar el codigo de recuperacion. Revisa la configuracion del correo e intenta de nuevo.",
            )
            return render(request, "password_reset_request.html", {"form_data": form_data})

        messages.success(
            request,
            f"Te enviamos un codigo de recuperacion a {usuario.correo}.",
        )
        return redirect("sesiones:password_reset_confirm", token=password_reset.token)

    return render(request, "password_reset_request.html", {"form_data": form_data})


def password_reset_confirm(request, token):
    password_reset = get_object_or_404(
        RecuperacionClave.objects.select_related("usuario"),
        token=token,
    )

    if request.method == "POST":
        if request.POST.get("action") == "resend":
            return _resend_password_reset_code(request, password_reset)

        verification_code = (request.POST.get("codigo") or "").strip()
        new_password = request.POST.get("clave") or ""
        confirm_password = request.POST.get("confirmar_clave") or ""

        if not verification_code or not new_password or not confirm_password:
            messages.error(request, "Completa el codigo y la nueva contrasena.")
        elif new_password != confirm_password:
            messages.error(request, "La confirmacion de la contrasena no coincide.")
        elif len(new_password) < 4:
            messages.error(request, "La nueva contrasena debe tener al menos 4 caracteres.")
        elif password_reset.codigo_expira_en <= timezone.now():
            messages.error(request, "El codigo ya vencio. Solicita uno nuevo para continuar.")
        elif not secret_matches(verification_code, password_reset.codigo):
            messages.error(request, "El codigo ingresado no es valido.")
        else:
            set_usuario_password(password_reset.usuario, new_password)
            password_reset.usuario.save(update_fields=["clave"])
            password_reset.delete()
            messages.success(
                request,
                "Tu contrasena fue actualizada correctamente. Ya puedes iniciar sesion.",
            )
            return redirect("sesiones:login")

    return render(
        request,
        "password_reset_confirm.html",
        {
            "password_reset": password_reset,
            "expires_in_minutes": _minutes_until_expiration(password_reset.codigo_expira_en),
        },
    )


def logout_view(request):
    request.session.flush()
    return redirect("sesiones:login")


def _build_registration_form_data(request):
    return {
        "documento": request.POST.get("documento", ""),
        "nombre": request.POST.get("nombre", ""),
        "apellido": request.POST.get("apellido", ""),
        "correo": normalize_email(request.POST.get("correo", "")),
        "fecha_nacimiento": request.POST.get("fecha_nacimiento") or request.POST.get("fechaNacimiento", ""),
    }


def _validate_registration_request(form_data, raw_password):
    if not form_data["documento"] or not form_data["nombre"] or not form_data["apellido"]:
        return _registration_error_context(
            form_data,
            "Completa todos los datos para continuar con el registro.",
        )
    if not form_data["correo"] or not form_data["fecha_nacimiento"] or not raw_password:
        return _registration_error_context(
            form_data,
            "Completa todos los datos para continuar con el registro.",
        )
    if not str(form_data["documento"]).isdigit():
        return _registration_error_context(
            form_data,
            "El documento debe contener solo numeros.",
        )
    if len(raw_password) < 4:
        return _registration_error_context(
            form_data,
            "La contrasena debe tener al menos 4 caracteres.",
        )
    if Usuario.objects.filter(documento=form_data["documento"]).exists():
        return _registration_error_context(
            form_data,
            "Ya existe una cuenta registrada con ese documento.",
            duplicate_documento=True,
        )
    if Usuario.objects.filter(correo__iexact=form_data["correo"]).exists():
        return _registration_error_context(
            form_data,
            "Ya existe una cuenta registrada con ese correo.",
            duplicate_correo=True,
        )
    return None


def _registration_error_context(form_data, message, **extra_context):
    extra_context["form_data"] = form_data
    extra_context["message"] = message
    return extra_context


def _save_pending_registration(*, form_data, raw_password, verification_code):
    matching_records = list(
        RegistroPendiente.objects.filter(
            Q(documento=form_data["documento"]) | Q(correo__iexact=form_data["correo"])
        ).order_by("-actualizado_en")
    )
    pending_registration = matching_records[0] if matching_records else RegistroPendiente()

    for stale_record in matching_records[1:]:
        stale_record.delete()

    pending_registration.documento = int(form_data["documento"])
    pending_registration.nombre = form_data["nombre"]
    pending_registration.apellido = form_data["apellido"]
    pending_registration.correo = form_data["correo"]
    pending_registration.fecha_nacimiento = form_data["fecha_nacimiento"]
    pending_registration.clave = hash_secret(raw_password)
    pending_registration.codigo = hash_secret(verification_code)
    pending_registration.codigo_expira_en = get_code_expiration()
    pending_registration.save()
    return pending_registration


def _resend_registration_code(request, pending_registration):
    verification_code = generate_verification_code()
    pending_registration.codigo = hash_secret(verification_code)
    pending_registration.codigo_expira_en = get_code_expiration()
    pending_registration.save(update_fields=["codigo", "codigo_expira_en", "actualizado_en"])

    try:
        send_registration_code_email(pending_registration.correo, verification_code)
    except MailDeliveryError:
        messages.error(
            request,
            "No fue posible reenviar el codigo en este momento. Intenta de nuevo mas tarde.",
        )
    else:
        messages.success(
            request,
            f"Enviamos un nuevo codigo de verificacion a {pending_registration.correo}.",
        )
    return redirect("sesiones:registro_verificar", token=pending_registration.token)


def _resend_password_reset_code(request, password_reset):
    verification_code = generate_verification_code()
    password_reset.codigo = hash_secret(verification_code)
    password_reset.codigo_expira_en = get_code_expiration()
    password_reset.save(update_fields=["codigo", "codigo_expira_en", "actualizado_en"])

    try:
        send_password_reset_code_email(password_reset.correo, verification_code)
    except MailDeliveryError:
        messages.error(
            request,
            "No fue posible reenviar el codigo de recuperacion. Intenta de nuevo mas tarde.",
        )
    else:
        messages.success(
            request,
            f"Enviamos un nuevo codigo de recuperacion a {password_reset.correo}.",
        )
    return redirect("sesiones:password_reset_confirm", token=password_reset.token)


def _minutes_until_expiration(expires_at):
    remaining_seconds = max(int((expires_at - timezone.now()).total_seconds()), 0)
    remaining_minutes = remaining_seconds // 60
    if remaining_seconds % 60:
        remaining_minutes += 1
    return max(remaining_minutes, 0)


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

from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
from django.core.mail import send_mail
import resend
from django.conf import settings

from apps.common.seo import apply_public_page_cache_headers, serialize_structured_data
from apps.ventas.models import SolicitudDevolucionVenta
from apps.sesiones.decorators import admin_required_session
from apps.sesiones.models import Usuario, PasswordResetToken


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
        
        # Validar longitudes mínimas
        if not documento or len(str(documento)) < 8:
            messages.error(request, "El documento debe tener al menos 8 dígitos.")
            return render(request, "login.html", {"next": next_url})
        
        if not clave or len(clave) < 8:
            messages.error(request, "La contraseña debe tener al menos 8 caracteres.")
            return render(request, "login.html", {"next": next_url})
        
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
        clave = request.POST.get("clave")
        correo = (request.POST.get("correo") or "").strip()
        form_data = {
            "documento": documento,
            "nombre": request.POST.get("nombre", ""),
            "apellido": request.POST.get("apellido", ""),
            "correo": correo,
            "fecha_nacimiento": request.POST.get("fecha_nacimiento") or request.POST.get("fechaNacimiento", ""),
        }

        # Validar longitudes mínimas
        if not documento or len(str(documento)) < 8:
            messages.error(request, "El documento debe tener al menos 8 dígitos.")
            return render(
                request,
                "registro.html",
                {"form_data": form_data},
            )

        if not clave or len(clave) < 8:
            messages.error(request, "La contraseña debe tener al menos 8 caracteres.")
            return render(
                request,
                "registro.html",
                {"form_data": form_data},
            )

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
            clave=clave,
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


def solicitar_reset_contrasena(request):
    """Vista para solicitar reseteo de contraseña"""
    if request.method == "POST":
        correo = request.POST.get("correo", "").strip()
        usuario = Usuario.objects.filter(correo__iexact=correo).first()
        
        if usuario:
            # Generar token
            reset_token = PasswordResetToken.generar_token_para_usuario(usuario)
            
            # Construir enlace de reseteo
            reset_url = request.build_absolute_uri(
                reverse("sesiones:confirmar_reset_contrasena", args=[reset_token.token])
            )
            
            # Enviar email
            asunto = "Recupera tu contraseña - Lotus Dream Spa"
            mensaje = f"""
            Hola {usuario.nombre},
            
            Hemos recibido una solicitud para resetear tu contraseña.
            
            Haz clic en el siguiente enlace para establecer una nueva contraseña:
            {reset_url}
            
            Este enlace expirará en 24 horas por razones de seguridad.
            
            Si no solicitaste este cambio, ignora este correo.
            
            Saludos,
            Lotus Dream Spa
            """
            
            
            try:
                resend.api_key = settings.RESEND_API_KEY
                resend.Emails.send({
                    "from": "Lotus Dream Spa <onboarding@resend.dev>",
                    "to": [usuario.correo],
                    "subject": asunto,
                    "text": mensaje,
                })
                messages.success(
                    request,
                    f"Se ha enviado un enlace de recuperación a {correo}. Revisa tu bandeja de entrada."
                )
            except Exception as e:
                messages.error(
                    request,
                    "Error al enviar el correo. Por favor, intenta más tarde."
                )
                
        else:
            # Por seguridad, no revelar si el correo existe
            messages.info(
                request,
                f"Si {correo} está registrado, recibirá un enlace de recuperación."
            )
        
        return redirect("sesiones:login")
    
    return render(request, "solicitar_reset_contrasena.html")


def confirmar_reset_contrasena(request, token):
    """Vista para confirmar y cambiar la contraseña"""
    reset_token = PasswordResetToken.objects.filter(token=token).first()
    
    if not reset_token or not reset_token.es_valido():
        messages.error(
            request,
            "El enlace de recuperación es inválido o ha expirado. Solicita uno nuevo."
        )
        return redirect("sesiones:solicitar_reset_contrasena")
    
    if request.method == "POST":
        nueva_contrasena = request.POST.get("nueva_contrasena", "").strip()
        confirmar_contrasena = request.POST.get("confirmar_contrasena", "").strip()
        
        if not nueva_contrasena:
            messages.error(request, "La contraseña no puede estar vacía.")
            return render(
                request,
                "confirmar_reset_contrasena.html",
                {"token": token}
            )
        
        if nueva_contrasena != confirmar_contrasena:
            messages.error(request, "Las contraseñas no coinciden.")
            return render(
                request,
                "confirmar_reset_contrasena.html",
                {"token": token}
            )
        
        if len(nueva_contrasena) < 6:
            messages.error(request, "La contraseña debe tener al menos 6 caracteres.")
            return render(
                request,
                "confirmar_reset_contrasena.html",
                {"token": token}
            )
        
        # Actualizar contraseña
        usuario = reset_token.usuario
        usuario.clave = nueva_contrasena
        usuario.save()
        
        # Marcar token como utilizado
        reset_token.marcar_como_utilizado()
        
        messages.success(request, "Tu contraseña ha sido actualizada correctamente.")
        return redirect("sesiones:login")
    
    return render(
        request,
        "confirmar_reset_contrasena.html",
        {"token": token}
    )

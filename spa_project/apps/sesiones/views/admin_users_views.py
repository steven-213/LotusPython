from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.sesiones.decorators import admin_required_session
from apps.sesiones.models import Usuario
from apps.citas.models import Reserva
from apps.ventas.models import Venta


def _usuario_duplicado(*, correo, documento, exclude_id=None):
    """Verifica si existe usuario con correo o documento duplicado"""
    filtros = Q(correo__iexact=correo) | Q(documento=documento)
    usuarios = Usuario.objects.filter(filtros)
    if exclude_id:
        usuarios = usuarios.exclude(id=exclude_id)
    return usuarios.first()


@admin_required_session
def usuarios_lista(request):
    """Lista todos los usuarios con búsqueda"""
    query = request.GET.get("q", "")
    usuarios = Usuario.objects.all().order_by("-fecha_registro")
    
    if query:
        usuarios = usuarios.filter(
            Q(nombre__icontains=query)
            | Q(apellido__icontains=query)
            | Q(correo__icontains=query)
            | Q(documento__icontains=query)
        )
    
    return render(
        request,
        "administrador/usuarios/lista.html",
        {"usuarios": usuarios, "query": query},
    )


@admin_required_session
def usuarios_nuevo(request):
    """Crea un nuevo usuario"""
    if request.method == "POST":
        documento = request.POST.get("documento", "").strip()
        nombre = request.POST.get("nombre", "").strip()
        apellido = request.POST.get("apellido", "").strip()
        correo = request.POST.get("correo", "").strip()
        fecha_nacimiento = request.POST.get("fecha_nacimiento", "").strip()
        telefono = request.POST.get("telefono", "").strip()
        clave = request.POST.get("clave", "").strip()
        rol = request.POST.get("rol", Usuario.ROL_CLIENTE).strip()
        
        # Validaciones
        if not documento:
            messages.error(request, "El documento es obligatorio.")
            return render(request, "administrador/usuarios/nuevo.html")
        
        if not nombre:
            messages.error(request, "El nombre es obligatorio.")
            return render(request, "administrador/usuarios/nuevo.html")
        
        if not apellido:
            messages.error(request, "El apellido es obligatorio.")
            return render(request, "administrador/usuarios/nuevo.html")
        
        if not correo:
            messages.error(request, "El correo es obligatorio.")
            return render(request, "administrador/usuarios/nuevo.html")
        
        if not fecha_nacimiento:
            messages.error(request, "La fecha de nacimiento es obligatoria.")
            return render(request, "administrador/usuarios/nuevo.html")
        
        if not clave or len(clave) < 8:
            messages.error(request, "La contraseña debe tener al menos 8 caracteres.")
            return render(request, "administrador/usuarios/nuevo.html")
        
        # Verificar duplicados
        usuario_existente = _usuario_duplicado(correo=correo, documento=documento)
        if usuario_existente:
            if usuario_existente.documento == int(documento):
                messages.error(request, "Ya existe un usuario con ese documento.")
            else:
                messages.error(request, "Ya existe un usuario con ese correo.")
            return render(request, "administrador/usuarios/nuevo.html")
        
        try:
            usuario = Usuario.objects.create(
                documento=int(documento),
                nombre=nombre,
                apellido=apellido,
                correo=correo,
                fecha_nacimiento=fecha_nacimiento,
                telefono=telefono if telefono else None,
                clave=clave,
                rol=rol,
                activo=True,
            )
            messages.success(request, f"Usuario {usuario.nombre} {usuario.apellido} creado correctamente.")
            return redirect("sesiones:usuarios_detalle", usuario_id=usuario.id)
        except ValueError:
            messages.error(request, "El documento debe ser un número válido.")
            return render(request, "administrador/usuarios/nuevo.html")
    
    return render(request, "administrador/usuarios/nuevo.html")


@admin_required_session
def usuarios_detalle(request, usuario_id):
    """Muestra los detalles de un usuario"""
    usuario = get_object_or_404(Usuario, id=usuario_id)
    return render(
        request,
        "administrador/usuarios/detalle.html",
        {"usuario": usuario},
    )


@admin_required_session
def usuarios_editar(request, usuario_id):
    """Edita un usuario existente"""
    usuario = get_object_or_404(Usuario, id=usuario_id)
    
    if request.method == "POST":
        nombre = request.POST.get("nombre", "").strip()
        apellido = request.POST.get("apellido", "").strip()
        correo = request.POST.get("correo", "").strip()
        fecha_nacimiento = request.POST.get("fecha_nacimiento", "").strip()
        telefono = request.POST.get("telefono", "").strip()
        rol = request.POST.get("rol", Usuario.ROL_CLIENTE).strip()
        activo = request.POST.get("activo") == "on"
        
        # Validaciones
        if not nombre:
            messages.error(request, "El nombre es obligatorio.")
            return render(request, "administrador/usuarios/editar.html", {"usuario": usuario})
        
        if not apellido:
            messages.error(request, "El apellido es obligatorio.")
            return render(request, "administrador/usuarios/editar.html", {"usuario": usuario})
        
        if not correo:
            messages.error(request, "El correo es obligatorio.")
            return render(request, "administrador/usuarios/editar.html", {"usuario": usuario})
        
        if not fecha_nacimiento:
            messages.error(request, "La fecha de nacimiento es obligatoria.")
            return render(request, "administrador/usuarios/editar.html", {"usuario": usuario})
        
        # Validar correo único
        usuario_existente = _usuario_duplicado(
            correo=correo,
            documento=usuario.documento,
            exclude_id=usuario.id,
        )
        if usuario_existente:
            messages.error(request, "Ya existe otro usuario con ese correo.")
            return render(request, "administrador/usuarios/editar.html", {"usuario": usuario})
        
        # Validar que no se elimine el único admin
        usuario_actual_id = request.session.get("usuario_id")
        if usuario.id == usuario_actual_id and not activo:
            messages.error(request, "No puedes desactivar tu propia cuenta.")
            return render(request, "administrador/usuarios/editar.html", {"usuario": usuario})
        
        # Si está quitando rol admin, verificar que no sea el único
        if usuario.rol == Usuario.ROL_ADMIN and rol != Usuario.ROL_ADMIN:
            admins_activos = Usuario.objects.filter(rol=Usuario.ROL_ADMIN, activo=True).exclude(id=usuario.id).count()
            if admins_activos == 0:
                messages.error(request, "No puedes cambiar el rol del único administrador activo.")
                return render(request, "administrador/usuarios/editar.html", {"usuario": usuario})
        
        usuario.nombre = nombre
        usuario.apellido = apellido
        usuario.correo = correo
        usuario.fecha_nacimiento = fecha_nacimiento
        usuario.telefono = telefono if telefono else None
        usuario.rol = rol
        usuario.activo = activo
        usuario.save()
        
        messages.success(request, f"Usuario {usuario.nombre} {usuario.apellido} actualizado correctamente.")
        return redirect("sesiones:usuarios_detalle", usuario_id=usuario.id)
    
    return render(request, "administrador/usuarios/editar.html", {"usuario": usuario})


@admin_required_session
def usuarios_eliminar(request, usuario_id):
    """Elimina un usuario con confirmación"""
    usuario = get_object_or_404(Usuario, id=usuario_id)
    usuario_actual_id = request.session.get("usuario_id")
    
    # Validación 1: No permitir eliminarse a sí mismo
    if usuario.id == usuario_actual_id:
        messages.error(request, "No puedes eliminar tu propia cuenta.")
        return redirect("sesiones:usuarios_lista")
    
    # Validación 2: No permitir eliminar el único admin activo
    if usuario.rol == Usuario.ROL_ADMIN and usuario.activo:
        admins_activos = Usuario.objects.filter(rol=Usuario.ROL_ADMIN, activo=True).exclude(id=usuario.id).count()
        if admins_activos == 0:
            messages.error(request, "No puedes eliminar el único administrador activo del sistema.")
            return redirect("sesiones:usuarios_detalle", usuario_id=usuario.id)
    
    if request.method == "POST":
        nombre_completo = f"{usuario.nombre} {usuario.apellido}"
        usuario.delete()
        messages.success(request, f"Usuario {nombre_completo} eliminado correctamente.")
        return redirect("sesiones:usuarios_lista")
    
    # GET: Mostrar página de confirmación
    return render(request, "administrador/usuarios/eliminar.html", {"usuario": usuario})


@admin_required_session
def usuarios_citas(request, usuario_id):
    """Muestra todas las citas agendadas de un usuario"""
    usuario = get_object_or_404(Usuario, id=usuario_id)
    citas = Reserva.objects.filter(cliente=usuario).select_related('servicio', 'profesional').order_by('-fecha_inicio')
    
    # Estadísticas de citas
    total_citas = citas.count()
    citas_confirmadas = citas.filter(estado=Reserva.ESTADO_CONFIRMADA).count()
    citas_finalizadas = citas.filter(estado=Reserva.ESTADO_FINALIZADA).count()
    
    context = {
        "usuario": usuario,
        "citas": citas,
        "total_citas": total_citas,
        "citas_confirmadas": citas_confirmadas,
        "citas_finalizadas": citas_finalizadas,
    }
    
    return render(
        request,
        "administrador/usuarios/citas.html",
        context,
    )


@admin_required_session
def usuarios_compras(request, usuario_id):
    """Muestra todas las compras realizadas por un usuario"""
    usuario = get_object_or_404(Usuario, id=usuario_id)
    ventas = Venta.objects.filter(cliente=usuario).prefetch_related('detalles__producto').order_by('-fecha')
    
    # Estadísticas de ventas
    total_ventas = ventas.count()
    total_gastado = sum(venta.total_factura for venta in ventas)
    
    # Agrupar productos comprados
    productos_comprados = []
    for venta in ventas:
        for detalle in venta.detalles.all():
            productos_comprados.append({
                'producto': detalle.producto,
                'cantidad': detalle.cantidad,
                'precio_unitario': detalle.precio_unitario,
                'venta': venta,
                'subtotal': detalle.cantidad * detalle.precio_unitario,
            })
    
    context = {
        "usuario": usuario,
        "ventas": ventas,
        "productos_comprados": productos_comprados,
        "total_ventas": total_ventas,
        "total_gastado": total_gastado,
    }
    
    return render(
        request,
        "administrador/usuarios/compras.html",
        context,
    )

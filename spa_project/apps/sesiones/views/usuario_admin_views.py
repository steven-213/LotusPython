from django.contrib import messages
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render

from apps.common.validation import (
    validate_basic_text,
    validate_birth_date,
    validate_digits_string,
    validate_email,
    validate_name,
    validate_password,
)
from apps.sesiones.decorators import admin_required_session
from apps.sesiones.models import Usuario


def _render_form(request, *, usuario=None):
    return render(
        request,
        "usuariosAdm/form.html",
        {
            "usuario_obj": usuario,
            "roles": Usuario.ROLES,
        },
    )


def _leer_usuario_form(request, *, usuario=None):
    documento = validate_digits_string(
        request.POST.get("documento"),
        label="El documento",
        min_length=3,
        max_length=15,
    )
    nombre = validate_name(request.POST.get("nombre"), label="El nombre")
    apellido = validate_name(request.POST.get("apellido"), label="El apellido")
    correo = validate_email(request.POST.get("correo"))
    fecha_nacimiento = validate_birth_date(request.POST.get("fecha_nacimiento"))
    rol = (request.POST.get("rol") or "").strip()
    if rol not in {choice[0] for choice in Usuario.ROLES}:
        raise ValueError("El rol seleccionado no es valido.")

    telefono = validate_digits_string(
        request.POST.get("telefono"),
        label="El telefono",
        min_length=10,
        max_length=10,
        required=False,
    )
    direccion = validate_basic_text(
        request.POST.get("direccion"),
        label="La direccion",
        min_length=5,
        max_length=120,
        required=False,
    )
    imagen_perfil = (request.POST.get("imagen_perfil") or "").strip()
    if len(imagen_perfil) > 200:
        raise ValueError("La URL de imagen no puede superar 200 caracteres.")

    clave = (request.POST.get("clave") or "").strip()
    if not usuario or clave:
        clave = validate_password(clave)
    else:
        clave = usuario.clave

    return {
        "documento": int(documento),
        "nombre": nombre,
        "apellido": apellido,
        "correo": correo,
        "fecha_nacimiento": fecha_nacimiento,
        "clave": clave,
        "rol": rol,
        "telefono": telefono,
        "direccion": direccion,
        "imagen_perfil": imagen_perfil or None,
        "activo": request.POST.get("activo", "off") == "on",
    }


def _validar_duplicados(datos, *, usuario=None):
    usuarios = Usuario.objects.filter(
        Q(documento=datos["documento"]) | Q(correo__iexact=datos["correo"])
    )
    if usuario:
        usuarios = usuarios.exclude(id=usuario.id)
    if usuarios.filter(documento=datos["documento"]).exists():
        raise ValueError("Ya existe un usuario con ese documento.")
    if usuarios.filter(correo__iexact=datos["correo"]).exists():
        raise ValueError("Ya existe un usuario con ese correo.")


@admin_required_session
def usuario_lista(request):
    query = (request.GET.get("q") or "").strip()
    rol = (request.GET.get("rol") or "").strip()
    estado = (request.GET.get("estado") or "").strip()

    usuarios = Usuario.objects.all().order_by("nombre", "apellido")
    if query:
        if len(query) < 3:
            messages.error(request, "La busqueda debe tener al menos 3 caracteres.")
            query = ""
        else:
            filtros = Q(nombre__icontains=query) | Q(apellido__icontains=query) | Q(correo__icontains=query)
            if query.isdigit():
                filtros |= Q(documento=int(query))
            usuarios = usuarios.filter(filtros)
    if rol in {choice[0] for choice in Usuario.ROLES}:
        usuarios = usuarios.filter(rol=rol)
    if estado == "activo":
        usuarios = usuarios.filter(activo=True)
    elif estado == "inactivo":
        usuarios = usuarios.filter(activo=False)

    return render(
        request,
        "usuariosAdm/listar.html",
        {
            "usuarios": usuarios,
            "query": query,
            "rol_filtro": rol,
            "estado_filtro": estado,
            "roles": Usuario.ROLES,
        },
    )


@admin_required_session
def usuario_nuevo(request):
    if request.method == "POST":
        try:
            datos = _leer_usuario_form(request)
            _validar_duplicados(datos)
            usuario = Usuario.objects.create(**datos)
        except ValueError as exc:
            messages.error(request, str(exc))
            return _render_form(request)

        messages.success(request, "Usuario creado correctamente.")
        return redirect("sesiones:usuario_detalle", usuario_id=usuario.id)
    return _render_form(request)


@admin_required_session
def usuario_detalle(request, usuario_id):
    usuario = get_object_or_404(Usuario, id=usuario_id)
    return render(request, "usuariosAdm/ver.html", {"usuario_obj": usuario})


@admin_required_session
def usuario_editar(request, usuario_id):
    usuario = get_object_or_404(Usuario, id=usuario_id)
    if request.method == "POST":
        try:
            datos = _leer_usuario_form(request, usuario=usuario)
            _validar_duplicados(datos, usuario=usuario)
        except ValueError as exc:
            messages.error(request, str(exc))
            return _render_form(request, usuario=usuario)

        for campo, valor in datos.items():
            setattr(usuario, campo, valor)
        usuario.save()
        messages.success(request, "Usuario actualizado correctamente.")
        return redirect("sesiones:usuario_detalle", usuario_id=usuario.id)
    return _render_form(request, usuario=usuario)


@admin_required_session
def usuario_eliminar(request, usuario_id):
    usuario = get_object_or_404(Usuario, id=usuario_id)
    if request.method == "POST":
        if usuario.id == request.session.get("usuario_id"):
            messages.error(request, "No puedes eliminar tu propia cuenta desde el CRUD administrativo.")
            return redirect("sesiones:usuario_detalle", usuario_id=usuario.id)
        try:
            usuario.delete()
            messages.success(request, "Usuario eliminado correctamente.")
        except ProtectedError:
            usuario.activo = False
            usuario.save(update_fields=["activo"])
            messages.warning(request, "El usuario tiene registros asociados; fue desactivado para conservar el historial.")
        return redirect("sesiones:usuario_lista")
    return redirect("sesiones:usuario_detalle", usuario_id=usuario.id)

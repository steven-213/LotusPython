from django.shortcuts import render, redirect, get_object_or_404
from .models import Users, Producto, Imagen
from django.contrib.auth import logout
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib import messages

def index(request):

    usuario = None

    if "usuario_id" in request.session:
        from .models import Users
        usuario = Users.objects.get(id=request.session["usuario_id"])

    return render(request, "index.html", {
        "usuario": usuario
    })


def conocenos(request):
    return render(request, 'conocenos.html')


def servicios(request):
    return render(request, 'servicios.html')


def compra(request):
    return render(request, 'compra.html')


def login_view(request):

    if request.method == "POST":

        documento = request.POST.get("documento")
        clave = request.POST.get("clave")

        try:
            usuario = Users.objects.get(documento=documento, clave=clave)

            request.session["usuario_id"] = usuario.id

            # redirección según tipo
            if documento == "123456":   # ejemplo admin
                return redirect("dashboard")
            else:
                return redirect("home")

        except Users.DoesNotExist:
            messages.error(request, "Documento o contraseña incorrectos")

    return render(request, "login.html")


def registro(request):

    if request.method == "POST":

        documento = request.POST.get("documento")
        nombre = request.POST.get("nombre")
        apellido = request.POST.get("apellido")
        correo = request.POST.get("correo")
        fechaNacimiento = request.POST.get("fechaNacimiento")
        clave = request.POST.get("clave")

        Users.objects.create(
            documento=documento,
            nombre=nombre,
            apellido=apellido,
            correo=correo,
            fechaNacimiento=fechaNacimiento,
            clave=clave
        )

        messages.success(request, "Usuario registrado correctamente")

        return redirect("login")

    return render(request, "registro.html")


def logout(request):

    request.session.flush()   # elimina la sesión
    return redirect("home")


def dashboard(request):
    return render(request, "dashboard.html")


def resultado(request):
    return render(request, "resultado.html")


def productos(request):
    lista_productos = Producto.objects.all()
    return render(request, "lista.html", {"productos": lista_productos})


def nuevo_producto(request):
    if request.method == "POST":
        nombre = request.POST.get("nombre")
        descripcion = request.POST.get("descripcion")
        precio = request.POST.get("precio")

        Producto.objects.create(
            nombre=nombre,
            descripcion=descripcion,
            precio=precio
        )

        return redirect("lista")

    return render(request, "nuevo.html")


def actualizar_producto(request, id):
    producto = get_object_or_404(Producto, id=id)

    if request.method == "POST":
        producto.nombre = request.POST.get("nombre")
        producto.descripcion = request.POST.get("descripcion")
        producto.precio = request.POST.get("precio")
        producto.save()

        return redirect("lista")

    return render(request, "actualizar.html", {"producto": producto})


def imagenes(request):
    lista_imagenes = Imagen.objects.all()
    return render(request, "imagenes.html", {"imagenes": lista_imagenes})
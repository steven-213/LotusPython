from pyexpat.errors import messages

from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.models import User


def index(request):
    return render(request, "index.html")

def dashboard(request):
    return render(request, "admin/dashboard.html")

def conocenos(request):
    return render(request, "conocenos.html")


def servicios(request):
    return render(request, "cliente/servicios.html")


def compra(request):
    return render(request, "cliente/compra.html")


def login_view(request):

    if request.method == "POST":

        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect("home")

    return render(request, "login.html")

def registro(request):

    if request.method == "POST":

        documento = request.POST.get("documento")
        nombre = request.POST.get("nombre")
        apellido = request.POST.get("apellido")
        correo = request.POST.get("correo")
        clave = request.POST.get("clave")

        # verificar si el usuario ya existe
        if User.objects.filter(username=documento).exists():
            messages.error(request, "Este documento ya está registrado")
            return redirect("registro")

        # crear usuario
        User.objects.create_user(
            username=documento,
            email=correo,
            password=clave,
            first_name=nombre,
            last_name=apellido
        )

        messages.success(request, "Cuenta creada correctamente. Ahora puedes iniciar sesión.")

        # redirige al login
        return redirect("login")

    return render(request, "registro.html")

def logout_view(request):
    logout(request)
    return redirect("home")


# PANEL SOLO ADMIN
@staff_member_required
def dashboard(request):
    return render(request, "dashboard.html")
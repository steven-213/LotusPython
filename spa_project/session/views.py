from django.shortcuts import render, redirect, get_object_or_404 
from models import Users
from django.http import HttpResponse
from django.contrib import messages

def login_view(request):
    if request.method == 'POST':
        pass
    context = {
        'titulo': 'Iniciar Sesión',
    }
    return render(request, 'login.html', context)

def login(request):
    if request.method == 'POST':
        documento = request.POST.get('documento')
        clave = request.POST.get('clave')
        usuario = Users.objects.filter(documento=documento, clave=clave).firs
    if usuario is not None:
        return render (request, 'index.html', {'usuario': usuario})
    else:
        messages.error (request, 'Documento o contraseña incorrectos.')
        return redirect('login') 
    return render (request, 'personas/login.html')
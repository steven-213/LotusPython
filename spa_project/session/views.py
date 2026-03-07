from django.shortcuts import render, redirect, get_object_or_404
from .models import Users, Producto, Servicio, Cita, Venta, Proveedor
from django.contrib.auth import logout
from django.contrib import messages
from django.contrib.auth import authenticate, login
import json
from django.utils.dateparse import parse_datetime
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


# ========================= VISTAS PRINCIPALES =========================

def index(request):
    usuario = None
    if "usuario_id" in request.session:
        from .models import Users
        usuario = Users.objects.get(id=request.session["usuario_id"])
    return render(request, "index.html", {"usuario": usuario})


def conocenos(request):
    return render(request, 'conocenos.html')


def servicios(request):  # servicios
    return render(request, 'cliente/servicios.html')


def compra(request):  # productos
    return render(request, 'cliente/compra.html')


# ========================= AUTENTICACIÓN =========================

def login_view(request):
    if request.method == "POST":
        documento = request.POST.get("documento")
        clave = request.POST.get("clave")
        try:
            usuario = Users.objects.get(documento=documento, clave=clave)
            request.session["usuario_id"] = usuario.id

            # redirección según tipo
            if documento == "123456":  # ejemplo admin
                return redirect("admin/dashboard")
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
    request.session.flush()  # elimina la sesión
    return redirect("home")


# ========================= DASHBOARD =========================

def dashboard(request):
    return render(request, "administrador/dashboard.html")


def calendario_view(request):
    return render(request, "administrador/calendar.html")

@csrf_exempt
def api_calendar(request):
    if request.method == "GET":
        citas = Cita.objects.all()
        data = [
            {
                "id": c.id,
                "title": c.title,
                "startDate": c.startDate.isoformat(),
                "endDate": c.endDate.isoformat(),
                "allDay": c.allDay
            } for c in citas
        ]
        return JsonResponse(data, safe=False)

    elif request.method == "POST":
        body = json.loads(request.body)
        title = body.get("title")
        startDate = parse_datetime(body.get("startDate"))
        endDate = parse_datetime(body.get("endDate"))
        allDay = body.get("allDay", False)

        cita = Cita.objects.create(
            title=title,
            startDate=startDate,
            endDate=endDate,
            allDay=allDay
        )

        return JsonResponse({
            "id": cita.id,
            "title": cita.title,
            "startDate": cita.startDate.isoformat(),
            "endDate": cita.endDate.isoformat(),
            "allDay": cita.allDay
        })


# ========================= API CITAS =========================

@csrf_exempt
def api_citas(request):
    if request.method == "GET":
        citas = Cita.objects.all()
        data = [
            {
                "id": c.id,
                "title": c.title,
                "startDate": c.startDate.isoformat(),
                "endDate": c.endDate.isoformat(),
                "allDay": c.allDay
            } for c in citas
        ]
        return JsonResponse(data, safe=False)

    elif request.method == "POST":
        body = json.loads(request.body)
        title = body.get("title")
        startDate = parse_datetime(body.get("startDate"))
        endDate = parse_datetime(body.get("endDate"))
        allDay = body.get("allDay", False)

        cita = Cita.objects.create(
            title=title,
            startDate=startDate,
            endDate=endDate,
            allDay=allDay
        )

        return JsonResponse({
            "id": cita.id,
            "title": cita.title,
            "startDate": cita.startDate.isoformat(),
            "endDate": cita.endDate.isoformat(),
            "allDay": cita.allDay
        })


# ========================= VENTAS =========================

def ventas_view(request):
    return render(request, "administrador/ventas.html")


@csrf_exempt
def api_ventas(request):
    if request.method == "GET":
        ventas = Venta.objects.all()
        data = [
            {
                "id": v.id,
                "title": f"{v.cliente} - ${v.total}",
                "startDate": v.fecha_inicio.isoformat(),
                "endDate": v.fecha_fin.isoformat(),
                "allDay": False
            } for v in ventas
        ]
        return JsonResponse(data, safe=False)

    elif request.method == "POST":
        body = json.loads(request.body)
        cliente = body.get("cliente")
        total = body.get("total")
        fecha_inicio = parse_datetime(body.get("startDate"))
        fecha_fin = parse_datetime(body.get("endDate"))
        descripcion = body.get("descripcion", "")

        venta = Venta.objects.create(
            cliente=cliente,
            total=total,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            descripcion=descripcion
        )

        return JsonResponse({
            "id": venta.id,
            "title": f"{venta.cliente} - ${venta.total}",
            "startDate": venta.fecha_inicio.isoformat(),
            "endDate": venta.fecha_fin.isoformat(),
            "allDay": False
        })


# ========================= RESULTADO CLIENTE =========================

def resultado(request):
    return render(request, "cliente/resultado.html")


# ========================= PRODUCTOS =========================

def lista_productos(request):
    productos = Producto.objects.all()
    return render(request, 'productosAdm/listaProductos.html', {'productos': productos})

def crear_productos(request):
    proveedores = Proveedor.objects.all()

    if request.method == 'POST':
        nombre = request.POST.get('nombre')
        descripcion = request.POST.get('descripcion')
        proveedor_id = request.POST.get('proveedor')
        stock = request.POST.get('stock')
        valor = request.POST.get('valor')
        precio = request.POST.get('precio')
        precioFinal = request.POST.get('precioFinal')

        proveedor = Proveedor.objects.get(id=proveedor_id)
        
        Producto.objects.create(
            nombre=nombre,
            descripcion=descripcion,
            proveedor=proveedor,
            stock=stock,
            valor=valor,
            precio=precio,
            precioFinal=precioFinal
        )

        return redirect('lista_productos')

    return render(request, 'productosAdm/formProductos.html', {'proveedores': proveedores})
def editar_producto(request, id):
    producto = get_object_or_404(Producto, id=id)
    proveedores = Proveedor.objects.all()

    if request.method == 'POST':
        producto.nombre = request.POST.get('nombre')
        producto.descripcion = request.POST.get('descripcion')
        producto.proveedor = Proveedor.objects.get(id=request.POST.get('proveedor'))
        producto.stock = request.POST.get('stock')
        producto.valor = request.POST.get('valor')
        producto.precio = request.POST.get('precio')
        producto.precioFinal = request.POST.get('precioFinal')
        producto.save()
        return redirect('lista_productos')

    return render(
        request,
        'productosAdm/formProductos.html',
        {
            'producto': producto,
            'proveedores': proveedores
        }
    )
    

def eliminar_producto(request, id):
    producto = get_object_or_404(Producto, id=id)

    if request.method == 'POST':
        producto.delete()
        return redirect('lista_productos')

    return render(request, 'productosAdm/eliminarProducto.html', {'producto': producto})

def buscar_producto(request):
    query = request.GET.get('q', '')

    if query:
        productos = Producto.objects.filter(nombre__icontains=query)
    else:
        productos = Producto.objects.all()

    return render(request, 'productosAdm/listaProductos.html', {
        'productos': productos,
        'query': query
    })


# ========================= SERVICIOS =========================

def servicios_lista(request):
    servicios = Servicio.objects.all()
    return render(request, "servicios/lista.html", {"servicios": servicios})


def servicio_nuevo(request):
    if request.method == "POST":
        nombre = request.POST['nombre']
        descripcion = request.POST['descripcion']
        precio = request.POST['precio']
        imagen = request.FILES.get('imagen')
        Servicio.objects.create(nombre=nombre, descripcion=descripcion, precio=precio, imagen=imagen)
        return redirect('servicios_lista')

    return render(request, "servicios/nuevo.html")


def detalle_servicio(request, id):
    servicio = get_object_or_404(Servicio, id=id)
    return render(request, "servicios/detalle.html", {"servicio": servicio})


def servicio_actualizar(request, id):
    servicio = get_object_or_404(Servicio, id=id)

    if request.method == "POST":
        servicio.nombre = request.POST['nombre']
        servicio.descripcion = request.POST['descripcion']
        servicio.precio = request.POST['precio']
        imagen = request.FILES.get('imagen')
        if imagen:
            servicio.imagen = imagen
        servicio.save()
        return redirect('servicios_lista')

    return render(request, "servicios/actualizar.html", {"servicio": servicio})
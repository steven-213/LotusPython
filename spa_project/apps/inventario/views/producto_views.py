import json
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models import Q
from django.urls import reverse
from decimal import Decimal

from apps.inventario.models import Producto, Proveedor
from apps.inventario.services import anotar_stock_disponible, obtener_stock_disponible
from apps.inventario.storage import subir_imagen_producto

from apps.sesiones.decorators import admin_required_session, login_required_session
from apps.sesiones.models import Usuario

from apps.ventas.models import DetalleVenta, ValidacionVenta, Venta
from apps.ventas.telegram_notifier import notificar_compra_pendiente



def productos_publicos(request):
    query = request.GET.get("q", "")

    productos = anotar_stock_disponible(
        Producto.objects.filter(activo=True).order_by("nombre")
    )

    if query:
        productos = productos.filter(nombre__icontains=query)

    return render(request, "cliente/compra.html", {
        "productos": productos,
        "query": query
    })


def procesar_pago(request):
    if "usuario_id" not in request.session:
        return JsonResponse(
            {
                "status": "error",
                "message": "Debes iniciar sesion para comprar.",
                "redirect_url": reverse("sesiones:login"),
            },
            status=401,
        )

    if request.method != "POST":
        return JsonResponse(
            {"status": "error", "message": "Metodo no permitido."},
            status=405,
        )

    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse(
            {"status": "error", "message": "No se pudo leer el carrito enviado."},
            status=400,
        )

    carrito = payload.get("carrito") or []
    if not isinstance(carrito, list) or not carrito:
        return JsonResponse(
            {"status": "error", "message": "Agrega al menos un producto al carrito."},
            status=400,
        )

    cliente = get_object_or_404(Usuario, id=request.session.get("usuario_id"))

    productos_ids = []
    cantidades_por_producto = {}
    for item in carrito:
        try:
            producto_id = int(item.get("id"))
            cantidad = int(item.get("cantidad") or 0)
        except (TypeError, ValueError):
            return JsonResponse(
                {"status": "error", "message": "Hay productos invalidos en el carrito."},
                status=400,
            )

        if cantidad <= 0:
            return JsonResponse(
                {"status": "error", "message": "La cantidad debe ser mayor a cero."},
                status=400,
            )

        productos_ids.append(producto_id)
        cantidades_por_producto[producto_id] = (
            cantidades_por_producto.get(producto_id, 0) + cantidad
        )

    productos = {
        producto.id: producto
        for producto in Producto.objects.filter(
            id__in=productos_ids,
            activo=True,
        )
    }

    if len(productos) != len(cantidades_por_producto):
        return JsonResponse(
            {
                "status": "error",
                "message": "Uno o varios productos ya no estan disponibles.",
            },
            status=400,
        )

    for producto_id, cantidad_total in cantidades_por_producto.items():
        producto = productos[producto_id]
        stock_disponible = obtener_stock_disponible(producto)
        if stock_disponible < cantidad_total:
            return JsonResponse(
                {
                    "status": "error",
                    "message": f"Solo quedan {stock_disponible} unidades de {producto.nombre}.",
                },
                status=400,
            )

    total = Decimal("0")
    for producto_id, cantidad_total in cantidades_por_producto.items():
        producto = productos[producto_id]
        total += producto.precio_venta * cantidad_total

    metodo_pago = (payload.get("metodo_pago") or "").strip() or "por_confirmar"
    telefono = (payload.get("telefono") or "").strip()
    direccion = (payload.get("direccion") or "").strip()

    observaciones = ["Compra creada desde catalogo web."]
    if telefono:
        observaciones.append(f"Telefono: {telefono}")
    if direccion:
        observaciones.append(f"Direccion: {direccion}")

    with transaction.atomic():
        venta = Venta.objects.create(
            cliente=cliente,
            total=total,
        )

        for producto_id, cantidad_total in cantidades_por_producto.items():
            producto = productos[producto_id]
            DetalleVenta.objects.create(
                venta=venta,
                producto=producto,
                cantidad=cantidad_total,
                precio_unitario=producto.precio_venta,
            )

        validacion = ValidacionVenta.objects.create(
            venta=venta,
            cliente=cliente,
            metodo_pago=metodo_pago,
            referencia_pago=f"WEB-{venta.id}",
            monto=total,
            estado="pendiente",
            observaciones="\n".join(observaciones),
        )

    sent = notificar_compra_pendiente(venta=venta, validacion=validacion)
    warning = ""
    if not sent:
        warning = "La compra fue registrada, pero no se pudo enviar la notificacion."

    return JsonResponse(
        {
            "status": "success",
            "redirect_url": reverse("inventario:resultado"),
            "warning": warning,
        }
    )


def resultado_compra(request):
    return render(request, "cliente/resultado.html")


@login_required_session
def producto_comprar(request, producto_id):

    if request.method != "POST":
        return redirect("inventario:productos_publicos")

    producto = get_object_or_404(Producto, id=producto_id)

    try:
        cantidad = int(request.POST.get("cantidad") or 1)
    except ValueError:
        cantidad = 1

    if cantidad < 1:
        cantidad = 1

    cliente = get_object_or_404(Usuario, id=request.session.get("usuario_id"))

    total = producto.precio_venta * cantidad

    venta = Venta.objects.create(
        cliente=cliente,
        total=total
    )

    DetalleVenta.objects.create(
        venta=venta,
        producto=producto,
        cantidad=cantidad,
        precio_unitario=producto.precio_venta,
    )

    validacion, created = ValidacionVenta.objects.get_or_create(
        venta_id=venta.id,
        defaults={
            "venta": venta,
            "cliente": cliente,
            "metodo_pago": "por_confirmar",
            "referencia_pago": f"WEB-{venta.id}",
            "monto": total,
            "estado": "pendiente",
            "observaciones": "Compra creada desde catalogo web.",
        }
    )

    if created:
        sent = notificar_compra_pendiente(venta=venta, validacion=validacion)

        if sent:
            messages.success(request, "Compra registrada. Pendiente de confirmación.")
        else:
            messages.warning(request, "Compra creada, pero no se pudo notificar.")

    else:
        messages.warning(request, "Ya existe una validación pendiente.")

    return redirect("sesiones:perfil")


@admin_required_session
def producto_lista(request):

    query = request.GET.get("q", "")
    estado_filtro = request.GET.get("estado", "")
    proveedor_id = request.GET.get("proveedor_id", "")

    productos = anotar_stock_disponible(
        Producto.objects.filter(activo=True).select_related("proveedor")
    )

    # búsqueda
    if query:
        productos = productos.filter(
            Q(nombre__icontains=query) |
            Q(descripcion__icontains=query)
        )

    # proveedor
    if proveedor_id:
        productos = productos.filter(proveedor_id=proveedor_id)

    proveedores = Proveedor.objects.all()

    productos_list = []
    for producto in productos:
        productos_list.append({
            "producto": producto,
            "margen": round(producto.margen_ganancia, 2),
        })

    return render(request, "inventario/dashboard/productos/lista.html", {
        "productos": productos_list,
        "query": query,
        "estado_filtro": estado_filtro,
        "proveedor_id": proveedor_id,
        "proveedores": proveedores,
    })


@admin_required_session
def producto_nuevo(request):

    if request.method == "POST":

        nombre = request.POST.get("nombre", "").strip()
        descripcion = request.POST.get("descripcion", "")
        precio_compra = request.POST.get("precio_compra") or 0
        impuesto = request.POST.get("impuesto") or 19
        margen_ganancia = request.POST.get("margen_ganancia") or 20
        proveedor_id = request.POST.get("proveedor_id")

        if not nombre:
            messages.error(request, "El nombre del producto es obligatorio")

            proveedores = Proveedor.objects.all()
            return render(request, "inventario/dashboard/productos/form.html", {
                "proveedores": proveedores
            })

        if Producto.objects.filter(nombre__iexact=nombre).exists():
            messages.error(request, "Ya existe un producto con ese nombre")

            proveedores = Proveedor.objects.all()
            return render(request, "inventario/dashboard/productos/form.html", {
                "proveedores": proveedores,
                "nombre": nombre,
                "descripcion": descripcion,
                "precio_compra": precio_compra,
                "impuesto": impuesto,
                "margen_ganancia": margen_ganancia,
            })

        if not proveedor_id:
            messages.error(request, "Debes seleccionar un proveedor")

            proveedores = Proveedor.objects.all()
            return render(request, "inventario/dashboard/productos/form.html", {
                "proveedores": proveedores,
                "nombre": nombre,
                "descripcion": descripcion,
                "precio_compra": precio_compra,
                "impuesto": impuesto,
                "margen_ganancia": margen_ganancia,
            })

        proveedor = get_object_or_404(Proveedor, id=proveedor_id)

        imagen_url = subir_imagen_producto(request.FILES.get("imagen"))

        Producto.objects.create(
            nombre=nombre,
            descripcion=descripcion,
            imagen=imagen_url,
            proveedor=proveedor,
            precio_compra=precio_compra,
            impuesto=impuesto,
            margen_ganancia=margen_ganancia,
        )

        messages.success(request, "Producto creado correctamente")
        return redirect("inventario:producto_lista")

    proveedores = Proveedor.objects.all()

    return render(request, "inventario/dashboard/productos/form.html", {
        "proveedores": proveedores
    })

@admin_required_session
def producto_editar(request, producto_id):

    producto = get_object_or_404(Producto, id=producto_id)

    if request.method == "POST":

        nombre = request.POST.get("nombre")

        if Producto.objects.filter(nombre__iexact=nombre).exclude(id=producto.id).exists():
            messages.error(request, "Ya existe otro producto con ese nombre")

            proveedores = Proveedor.objects.all()
            return render(request, "inventario/dashboard/productos/form.html", {
                "producto": producto,
                "proveedores": proveedores
            })

        proveedor_id = request.POST.get("proveedor_id")

        producto.nombre = nombre
        producto.descripcion = request.POST.get("descripcion", "")

        producto.precio_compra = Decimal(request.POST.get("precio_compra") or 0)
        producto.impuesto = Decimal(request.POST.get("impuesto") or 19)
        producto.margen_ganancia = Decimal(request.POST.get("margen_ganancia") or 20)

        imagen_url = subir_imagen_producto(request.FILES.get("imagen"))
        if imagen_url:
            producto.imagen = imagen_url

        producto.proveedor = Proveedor.objects.filter(id=proveedor_id).first() if proveedor_id else None

        producto.save()

        return redirect("inventario:producto_lista")

    proveedores = Proveedor.objects.all()

    return render(request, "inventario/dashboard/productos/form.html", {
        "producto": producto,
        "proveedores": proveedores
    })

@admin_required_session
def producto_detalle(request, producto_id):

    producto = get_object_or_404(
        anotar_stock_disponible(Producto.objects.select_related("proveedor")),
        id=producto_id,
    )

    return render(request, "inventario/dashboard/productos/detalle.html", {
        "producto": producto,
        "margen": producto.margen_ganancia
    })



@admin_required_session
def producto_eliminar(request, producto_id):

    producto = get_object_or_404(Producto, id=producto_id)

    if request.method == "POST":
        producto.activo = False
        producto.save()

    return redirect("inventario:producto_lista")

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models import Q
from decimal import Decimal

from apps.inventario.models import Producto, Proveedor
from apps.inventario.storage import subir_imagen_producto

from apps.sesiones.decorators import admin_required_session, login_required_session
from apps.sesiones.models import Usuario

from apps.ventas.models import DetalleVenta, ValidacionVenta, Venta
from apps.ventas.telegram_notifier import notificar_compra_pendiente



def productos_publicos(request):
    query = request.GET.get("q", "")

    productos = Producto.objects.all().order_by("nombre")

    if query:
        productos = productos.filter(nombre__icontains=query)

    return render(request, "cliente/compra.html", {
        "productos": productos,
        "query": query
    })


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

    productos = Producto.objects.filter(activo=True)

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

    producto = get_object_or_404(Producto, id=producto_id)

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
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from apps.inventario.models import Producto, Proveedor
from apps.sesiones.decorators import admin_required_session, login_required_session
from apps.sesiones.models import Usuario
from apps.ventas.models import DetalleVenta, ValidacionVenta, Venta
from apps.ventas.telegram_notifier import notify_pending_purchase


def productos_publicos(request):
    query = request.GET.get("q", "")
    productos = Producto.objects.filter(stock__gt=0).order_by("nombre")
    if query:
        productos = productos.filter(nombre__icontains=query)
    return render(request, "cliente/compra.html", {"productos": productos, "query": query})


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

    if producto.stock < cantidad:
        messages.error(request, "No hay stock suficiente para esa cantidad.")
        return redirect("inventario:productos_publicos")

    cliente = get_object_or_404(Usuario, id=request.session.get("usuario_id"))
    total = producto.precio_venta * cantidad
    venta = Venta.objects.create(cliente=cliente, total=total)
    DetalleVenta.objects.create(
        venta=venta,
        producto=producto,
        cantidad=cantidad,
        precio_unitario=producto.precio_venta,
    )
    validacion = ValidacionVenta.objects.create(
        venta=venta,
        cliente=cliente,
        metodo_pago="por_confirmar",
        referencia_pago=f"WEB-{venta.id}",
        monto=total,
        estado="pendiente",
        observaciones="Compra creada desde catalogo web, pendiente confirmacion por Telegram.",
    )
    sent = notify_pending_purchase(venta=venta, validacion=validacion)
    if sent:
        messages.success(request, "Compra registrada. Quedo pendiente de confirmacion por Telegram.")
    else:
        messages.warning(
            request,
            "Compra pendiente creada, pero no se pudo enviar la notificacion a Telegram. "
            "Revisa TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID.",
        )
    return redirect("sesiones:perfil")


@admin_required_session
def producto_lista(request):
    query = request.GET.get("q", "")
    productos = Producto.objects.all()
    if query:
        productos = productos.filter(nombre__icontains=query)
    return render(request, "inventario/productos/lista.html", {"productos": productos, "query": query})


@admin_required_session
def producto_nuevo(request):
    if request.method == "POST":
        proveedor_id = request.POST.get("proveedor_id")
        proveedor = Proveedor.objects.filter(id=proveedor_id).first() if proveedor_id else None
        Producto.objects.create(
            nombre=request.POST.get("nombre"),
            descripcion=request.POST.get("descripcion", ""),
            stock=request.POST.get("stock") or 0,
            proveedor=proveedor,
            precio_compra=request.POST.get("precio_compra") or 0,
            precio_venta=request.POST.get("precio_venta") or 0,
            iva=request.POST.get("iva") or 0,
        )
        return redirect("inventario:producto_lista")
    proveedores = Proveedor.objects.all()
    return render(request, "inventario/productos/form.html", {"proveedores": proveedores})


@admin_required_session
def producto_editar(request, producto_id):
    producto = get_object_or_404(Producto, id=producto_id)
    if request.method == "POST":
        proveedor_id = request.POST.get("proveedor_id")
        producto.nombre = request.POST.get("nombre")
        producto.descripcion = request.POST.get("descripcion", "")
        producto.stock = request.POST.get("stock") or 0
        producto.precio_compra = request.POST.get("precio_compra") or 0
        producto.precio_venta = request.POST.get("precio_venta") or 0
        producto.iva = request.POST.get("iva") or 0
        producto.proveedor = Proveedor.objects.filter(id=proveedor_id).first() if proveedor_id else None
        producto.save()
        return redirect("inventario:producto_lista")
    proveedores = Proveedor.objects.all()
    return render(
        request,
        "inventario/productos/form.html",
        {"producto": producto, "proveedores": proveedores},
    )


@admin_required_session
def producto_detalle(request, producto_id):
    producto = get_object_or_404(Producto, id=producto_id)
    return render(request, "inventario/productos/detalle.html", {"producto": producto})


@admin_required_session
def producto_eliminar(request, producto_id):
    producto = get_object_or_404(Producto, id=producto_id)
    if request.method == "POST":
        producto.delete()
    return redirect("inventario:producto_lista")

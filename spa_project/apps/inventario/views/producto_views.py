from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models import F, Q

from apps.inventario.models import Producto, Proveedor
from apps.inventario.storage import subir_imagen_producto
from apps.sesiones.decorators import admin_required_session, login_required_session
from apps.sesiones.models import Usuario
from apps.ventas.models import DetalleVenta, ValidacionVenta, Venta
from apps.ventas.telegram_notifier import notificar_compra_pendiente


def productos_publicos(request):
    query = request.GET.get("q", "")
    productos = Producto.objects.filter(stock__gt=0).order_by("nombre")
    if query:
        productos = productos.filter(nombre__icontains=query)
    return render(request, "cliente/compra.html", {"productos": productos, "query": query})


@login_required_session
def producto_comprar(request, producto_id):
    # Crea venta y validacion pendiente desde el catalogo publico.
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
    
    # Crear UNA SOLA validación con estado="pendiente"
    # No crear múltiples validaciones
    validacion, created = ValidacionVenta.objects.get_or_create(
        venta_id=venta.id,
        defaults={
            "venta": venta,
            "cliente": cliente,
            "metodo_pago": "por_confirmar",
            "referencia_pago": f"WEB-{venta.id}",
            "monto": total,
            "estado": "pendiente",  # SOLO con estado="pendiente"
            "observaciones": "Compra creada desde catalogo web, pendiente confirmacion.",
        }
    )
    
    # Log: Estado al crear
    print(f"🔍 [producto_comprar] Validacion {validacion.id} CREADA con estado: '{validacion.estado}'")
    
    # Solo notificar si es la PRIMERA creación
    if created:
        print(f"📤 [producto_comprar] Enviando notificación Telegram para validacion {validacion.id}...")
        sent = notificar_compra_pendiente(venta=venta, validacion=validacion)
        
        # Verificar estado DESPUÉS de enviar
        validacion.refresh_from_db()
        print(f"🔍 [producto_comprar] Estado DESPUÉS de notificar: '{validacion.estado}'")
        
        if sent:
            messages.success(request, "Compra registrada. Quedo pendiente de confirmacion.")
        else:
            messages.warning(
                request,
                "Compra pendiente creada, pero no se pudo enviar la notificacion a Telegram. "
                "Revisa TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID.",
            )
    else:
        messages.warning(request, "Ya existe una validacion pendiente para esta venta.")
    
    return redirect("sesiones:perfil")


@admin_required_session
def producto_lista(request):
    query = request.GET.get("q", "")
    estado_filtro = request.GET.get("estado", "")  # "activo", "inactivo", "bajo_stock", "sin_stock"
    proveedor_id = request.GET.get("proveedor_id", "")
    
    productos = Producto.objects.all()
    
    # Filtro por búsqueda
    if query:
        productos = productos.filter(
            Q(nombre__icontains=query) | Q(descripcion__icontains=query)
        )
    
    # Filtro por estado
    if estado_filtro == "activo":
        productos = productos.filter(activo=True)
    elif estado_filtro == "inactivo":
        productos = productos.filter(activo=False)
    elif estado_filtro == "bajo_stock":
        productos = productos.filter(Q(stock__lte=F("stock_minimo")) & Q(stock__gt=0))
    elif estado_filtro == "sin_stock":
        productos = productos.filter(stock=0)
    
    # Filtro por proveedor
    if proveedor_id:
        productos = productos.filter(proveedor_id=proveedor_id)
    
    # Contar estados
    sin_stock = Producto.objects.filter(stock=0).count()
    stock_bajo = Producto.objects.filter(stock__gt=0, stock__lte=F("stock_minimo")).count()
    
    # Obtener proveedores para el filtro
    proveedores = Proveedor.objects.all()
    
    # Agregar propiedades calculadas
    productos_list = []
    for producto in productos:
        productos_list.append({
            "producto": producto,
            "margen": round(producto.margen_ganancia, 2),
            "necesita_reorden": producto.necesita_reorden
        })
    
    return render(request, "inventario/productos/lista.html", {
        "productos": productos_list,
        "query": query,
        "sin_stock": sin_stock,
        "stock_bajo": stock_bajo,
        "estado_filtro": estado_filtro,
        "proveedor_id": proveedor_id,
        "proveedores": proveedores,
    })


@admin_required_session
def producto_nuevo(request):
    if request.method == "POST":
        proveedor_id = request.POST.get("proveedor_id")
        proveedor = Proveedor.objects.filter(id=proveedor_id).first() if proveedor_id else None
        imagen_url = subir_imagen_producto(request.FILES.get("imagen"))
        Producto.objects.create(
            nombre=request.POST.get("nombre"),
            descripcion=request.POST.get("descripcion", ""),
            imagen=imagen_url,
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
        imagen_url = subir_imagen_producto(request.FILES.get("imagen"))
        if imagen_url:
            producto.imagen = imagen_url
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
    margen = 0
    if producto.precio_compra > 0:
        margen = ((producto.precio_venta - producto.precio_compra) / producto.precio_compra) * 100
    return render(request, "inventario/productos/detalle.html", {"producto": producto, "margen": margen})


@admin_required_session
def producto_eliminar(request, producto_id):
    producto = get_object_or_404(Producto, id=producto_id)
    if request.method == "POST":
        producto.delete()
    return redirect("inventario:producto_lista")

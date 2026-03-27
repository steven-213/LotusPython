import json
from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.common.currency import parse_money
from apps.inventario.models import Producto, Proveedor
from apps.inventario.services import descontar_stock, obtener_stock_disponible, registrar_ingreso
from apps.inventario.storage import subir_imagen_producto
from apps.sesiones.decorators import admin_required_session, login_required_session
from apps.sesiones.models import Usuario
from apps.ventas.models import DetalleVenta, ValidacionVenta, Venta
from apps.ventas.telegram_notifier import notificar_compra_pendiente


def productos_publicos(request):
    query = request.GET.get("q", "")
    productos_qs = Producto.objects.filter(activo=True).order_by("nombre")
    if query:
        productos_qs = productos_qs.filter(nombre__icontains=query)

    productos = []
    for producto in productos_qs:
        producto.stock_disponible = obtener_stock_disponible(producto)
        if producto.stock_disponible > 0:
            productos.append(producto)

    return render(
        request,
        "cliente/compra.html",
        {"productos": productos, "query": query},
    )


@login_required_session
def resultado(request):
    return render(request, "cliente/resultado.html")


@login_required_session
def producto_comprar(request, producto_id):
    if request.method != "POST":
        return redirect("inventario:productos_publicos")

    producto = get_object_or_404(Producto, id=producto_id, activo=True)
    try:
        cantidad = int(request.POST.get("cantidad") or 1)
    except ValueError:
        cantidad = 1
    if cantidad < 1:
        cantidad = 1

    stock_disponible = obtener_stock_disponible(producto)
    if stock_disponible < cantidad:
        messages.error(request, "No hay stock suficiente para esa cantidad.")
        return redirect("inventario:productos_publicos")

    cliente = get_object_or_404(Usuario, id=request.session.get("usuario_id"))
    try:
        venta, validacion, sent = _crear_venta_pendiente(
            cliente=cliente,
            carrito=[{"id": producto.id, "cantidad": cantidad}],
            metodo_pago="por_confirmar",
            origen="compra directa desde catalogo web",
        )
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("inventario:productos_publicos")

    if sent:
        messages.success(
            request,
            f"Compra #{venta.id} registrada. Quedo pendiente de confirmacion.",
        )
    else:
        messages.warning(
            request,
            "Compra pendiente creada, pero no se pudo enviar la notificacion a Telegram. "
            "Revisa TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID.",
        )

    return redirect("sesiones:perfil")


def procesar_pago(request):
    if request.method != "POST":
        return JsonResponse(
            {"status": "error", "message": "Metodo no permitido."},
            status=405,
        )

    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        return JsonResponse(
            {
                "status": "error",
                "message": "Tu sesion expiro. Inicia sesion para continuar.",
                "redirect_url": "/sesiones/login/",
            },
            status=401,
        )

    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse(
            {"status": "error", "message": "No se pudo leer el carrito enviado."},
            status=400,
        )

    carrito = data.get("carrito") or []
    metodo_pago = (data.get("metodo_pago") or "").strip() or "por_confirmar"
    telefono = (data.get("telefono") or "").strip()
    direccion = (data.get("direccion") or "").strip()

    cliente = get_object_or_404(Usuario, id=usuario_id)

    try:
        venta, validacion, sent = _crear_venta_pendiente(
            cliente=cliente,
            carrito=carrito,
            metodo_pago=metodo_pago,
            telefono=telefono,
            direccion=direccion,
            origen="carrito web",
        )
    except ValueError as exc:
        return JsonResponse({"status": "error", "message": str(exc)}, status=400)
    except Exception:
        return JsonResponse(
            {
                "status": "error",
                "message": "Ocurrio un error inesperado al registrar la compra.",
            },
            status=500,
        )

    response = {
        "status": "success",
        "venta_id": venta.id,
        "validacion_id": validacion.id,
        "message": "Compra registrada y enviada para confirmacion.",
    }
    if not sent:
        response["warning"] = (
            "La compra quedo creada, pero no se pudo enviar la notificacion a Telegram."
        )
    return JsonResponse(response)


@admin_required_session
def producto_lista(request):
    query = request.GET.get("q", "")
    estado_filtro = request.GET.get("estado", "")
    proveedor_id = request.GET.get("proveedor_id", "")

    productos = Producto.objects.select_related("proveedor").all()

    if query:
        productos = productos.filter(
            Q(nombre__icontains=query) | Q(descripcion__icontains=query)
        )

    if estado_filtro == "activo":
        productos = productos.filter(activo=True)
    elif estado_filtro == "inactivo":
        productos = productos.filter(activo=False)

    if proveedor_id:
        productos = productos.filter(proveedor_id=proveedor_id)

    proveedores = Proveedor.objects.all()

    productos_list = []
    for producto in productos:
        stock_disponible = obtener_stock_disponible(producto)
        necesita_reorden = stock_disponible <= producto.stock_minimo
        productos_list.append(
            {
                "producto": producto,
                "margen": round(float(producto.margen_ganancia or 0), 2),
                "necesita_reorden": necesita_reorden,
                "stock_disponible": stock_disponible,
            }
        )

    if estado_filtro == "bajo_stock":
        productos_list = [
            item
            for item in productos_list
            if 0 < item["stock_disponible"] <= item["producto"].stock_minimo
        ]
    elif estado_filtro == "sin_stock":
        productos_list = [item for item in productos_list if item["stock_disponible"] == 0]

    sin_stock = sum(1 for item in productos_list if item["stock_disponible"] == 0)
    stock_bajo = sum(
        1
        for item in productos_list
        if 0 < item["stock_disponible"] <= item["producto"].stock_minimo
    )

    return render(
        request,
        "inventario/dashboard/productos/lista.html",
        {
            "productos": productos_list,
            "query": query,
            "sin_stock": sin_stock,
            "stock_bajo": stock_bajo,
            "estado_filtro": estado_filtro,
            "proveedor_id": proveedor_id,
            "proveedores": proveedores,
        },
    )


@admin_required_session
def producto_nuevo(request):
    if request.method == "POST":
        proveedor_id = request.POST.get("proveedor_id")
        proveedor = Proveedor.objects.filter(id=proveedor_id).first() if proveedor_id else None
        imagen_url = subir_imagen_producto(request.FILES.get("imagen"))
        stock_inicial = int(request.POST.get("stock") or 0)

        producto = Producto.objects.create(
            nombre=request.POST.get("nombre"),
            descripcion=request.POST.get("descripcion", ""),
            imagen=imagen_url,
            proveedor=proveedor,
            precio_compra=parse_money(request.POST.get("precio_compra")),
            precio_venta=parse_money(request.POST.get("precio_venta")),
            iva=request.POST.get("iva") or 0,
            margen_ganancia=_calcular_margen(
                parse_money(request.POST.get("precio_compra")),
                parse_money(request.POST.get("precio_venta")),
            ),
        )
        if stock_inicial > 0:
            registrar_ingreso(producto, stock_inicial, lote=f"INICIAL-{producto.id}")
        return redirect("inventario:producto_lista")

    proveedores = Proveedor.objects.all()
    return render(
        request,
        "inventario/dashboard/productos/form.html",
        {"proveedores": proveedores},
    )


@admin_required_session
def producto_editar(request, producto_id):
    producto = get_object_or_404(Producto, id=producto_id)
    if request.method == "POST":
        proveedor_id = request.POST.get("proveedor_id")
        stock_nuevo = int(request.POST.get("stock") or 0)
        stock_anterior = producto.stock

        producto.nombre = request.POST.get("nombre")
        producto.descripcion = request.POST.get("descripcion", "")
        producto.precio_compra = parse_money(request.POST.get("precio_compra"))
        producto.precio_venta = parse_money(request.POST.get("precio_venta"))
        producto.iva = request.POST.get("iva") or 0
        producto.margen_ganancia = _calcular_margen(producto.precio_compra, producto.precio_venta)
        imagen_url = subir_imagen_producto(request.FILES.get("imagen"))
        if imagen_url:
            producto.imagen = imagen_url
        producto.proveedor = Proveedor.objects.filter(id=proveedor_id).first() if proveedor_id else None
        producto.save()

        delta_stock = stock_nuevo - stock_anterior
        if delta_stock > 0:
            registrar_ingreso(producto, delta_stock, lote=f"AJUSTE-{producto.id}")
        elif delta_stock < 0:
            try:
                descontar_stock(producto, abs(delta_stock))
            except ValueError:
                messages.error(
                    request,
                    "No se pudo aplicar la reduccion manual porque el stock por lotes no alcanza.",
                )
                return redirect("inventario:producto_editar", producto_id=producto.id)

        return redirect("inventario:producto_lista")

    proveedores = Proveedor.objects.all()
    return render(
        request,
        "inventario/dashboard/productos/form.html",
        {"producto": producto, "proveedores": proveedores},
    )


@admin_required_session
def producto_detalle(request, producto_id):
    producto = get_object_or_404(Producto, id=producto_id)
    margen = 0
    if producto.precio_compra > 0:
        margen = ((producto.precio_venta - producto.precio_compra) / producto.precio_compra) * 100
    return render(
        request,
        "inventario/dashboard/productos/detalle.html",
        {"producto": producto, "margen": margen},
    )


@admin_required_session
def producto_eliminar(request, producto_id):
    producto = get_object_or_404(Producto, id=producto_id)
    if request.method == "POST":
        producto.delete()
    return redirect("inventario:producto_lista")


def _calcular_margen(precio_compra, precio_venta):
    precio_compra = Decimal(precio_compra or 0)
    precio_venta = Decimal(precio_venta or 0)
    if precio_compra <= 0:
        return Decimal("0")
    return ((precio_venta - precio_compra) / precio_compra) * Decimal("100")


def _crear_venta_pendiente(
    *,
    cliente,
    carrito,
    metodo_pago,
    telefono="",
    direccion="",
    origen="catalogo web",
):
    items = _normalizar_carrito(carrito)
    productos = Producto.objects.filter(id__in=items.keys(), activo=True).in_bulk()

    faltantes = [str(producto_id) for producto_id in items if producto_id not in productos]
    if faltantes:
        raise ValueError("Uno o varios productos del carrito ya no estan disponibles.")

    total = Decimal("0")
    detalles = []
    for producto_id, cantidad in items.items():
        producto = productos[producto_id]
        stock_disponible = obtener_stock_disponible(producto)
        if stock_disponible < cantidad:
            raise ValueError(
                f"No hay stock suficiente para {producto.nombre}. Disponible: {stock_disponible}."
            )

        precio_unitario = Decimal(producto.precio_venta or 0)
        detalles.append(
            {
                "producto": producto,
                "cantidad": cantidad,
                "precio_unitario": precio_unitario,
            }
        )
        total += precio_unitario * cantidad

    observaciones = [f"Origen: {origen}."]
    if telefono:
        observaciones.append(f"Telefono de contacto: {telefono}.")
    if direccion:
        observaciones.append(f"Direccion de entrega: {direccion}.")

    with transaction.atomic():
        venta = Venta.objects.create(cliente=cliente, total=total)
        for detalle in detalles:
            DetalleVenta.objects.create(
                venta=venta,
                producto=detalle["producto"],
                cantidad=detalle["cantidad"],
                precio_unitario=detalle["precio_unitario"],
            )

        validacion = ValidacionVenta.objects.create(
            venta=venta,
            cliente=cliente,
            metodo_pago=metodo_pago,
            referencia_pago=f"WEB-{venta.id}",
            monto=total,
            estado="pendiente",
            observaciones=" ".join(observaciones),
        )

    sent = notificar_compra_pendiente(venta=venta, validacion=validacion)
    return venta, validacion, sent


def _normalizar_carrito(carrito):
    if not isinstance(carrito, list) or not carrito:
        raise ValueError("El carrito esta vacio.")

    items = {}
    for item in carrito:
        try:
            producto_id = int(item.get("id"))
            cantidad = int(item.get("cantidad"))
        except (AttributeError, TypeError, ValueError):
            raise ValueError("Se recibio un carrito invalido.")

        if producto_id <= 0 or cantidad <= 0:
            raise ValueError("Cada producto del carrito debe tener una cantidad valida.")

        items[producto_id] = items.get(producto_id, 0) + cantidad

    return items

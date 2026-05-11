from django.shortcuts import get_object_or_404, redirect, render

from apps.inventario.models import Compra, DetalleCompra, DevolucionCompra, Producto, Proveedor, Inventario, MovimientoInventario
from apps.sesiones.decorators import admin_required_session

from django.db.models import Q
from django.db.models import Sum
from datetime import datetime, timedelta
from django.db import transaction
from decimal import Decimal, InvalidOperation
from django.contrib import messages
from apps.ventas.models import SolicitudDevolucionVenta


def _parse_positive_int(value, *, label):
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f"{label} debe ser un numero entero valido.")

    if parsed <= 0:
        raise ValueError(f"{label} debe ser mayor a cero.")
    return parsed


def _parse_decimal(value, *, label, allow_zero=False):
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError, TypeError, ValueError):
        raise ValueError(f"{label} debe ser un numero valido.")

    if allow_zero:
        if parsed < 0:
            raise ValueError(f"{label} no puede ser negativo.")
    elif parsed <= 0:
        raise ValueError(f"{label} debe ser mayor a cero.")
    return parsed


def _compra_factura_duplicada(*, proveedor, numero_factura, exclude_id=None):
    if not numero_factura:
        return False

    compras = Compra.objects.filter(
        proveedor=proveedor,
        numero_factura__iexact=numero_factura,
    )
    if exclude_id:
        compras = compras.exclude(id=exclude_id)
    return compras.exists()


def _obtener_detalles_compra(request):
    productos_ids = request.POST.getlist("productos_ids[]")
    cantidades = request.POST.getlist("cantidades[]")
    precios = request.POST.getlist("precios[]")
    impuestos = request.POST.getlist("impuestos[]")
    margenes = request.POST.getlist("margenes[]")
    lotes = request.POST.getlist("lotes[]")

    total_filas = max(
        len(productos_ids),
        len(cantidades),
        len(precios),
        len(impuestos),
        len(margenes),
        len(lotes),
        0,
    )

    detalles = []
    filas_duplicadas = set()

    for index in range(total_filas):
        producto_id = (productos_ids[index] if index < len(productos_ids) else "").strip()
        cantidad_raw = (cantidades[index] if index < len(cantidades) else "").strip()
        precio_raw = (precios[index] if index < len(precios) else "").strip()
        impuesto_raw = (impuestos[index] if index < len(impuestos) else "").strip()
        margen_raw = (margenes[index] if index < len(margenes) else "").strip()
        lote = (lotes[index] if index < len(lotes) else "").strip()

        if not any([producto_id, cantidad_raw, precio_raw, impuesto_raw, margen_raw, lote]):
            continue

        fila = index + 1
        if not producto_id:
            raise ValueError(f"Debes seleccionar un producto en la fila {fila}.")
        if not lote:
            raise ValueError(f"Debes ingresar un lote en la fila {fila}.")

        producto = Producto.objects.filter(id=producto_id, activo=True).first()
        if not producto:
            raise ValueError(f"El producto de la fila {fila} no es valido.")

        cantidad = _parse_positive_int(cantidad_raw, label=f"La cantidad de la fila {fila}")
        precio_compra = _parse_decimal(precio_raw, label=f"El precio de la fila {fila}")
        impuesto = _parse_decimal(
            impuesto_raw or "0",
            label=f"El impuesto de la fila {fila}",
            allow_zero=True,
        )
        margen_ganancia = _parse_decimal(
            margen_raw or "0",
            label=f"El margen de la fila {fila}",
            allow_zero=True,
        )

        duplicate_key = (producto.id, lote.casefold())
        if duplicate_key in filas_duplicadas:
            raise ValueError(
                f"El producto {producto.nombre} con lote {lote} esta repetido en la compra."
            )
        filas_duplicadas.add(duplicate_key)

        detalles.append(
            {
                "producto": producto,
                "cantidad": cantidad,
                "precio_compra": precio_compra,
                "impuesto": impuesto,
                "margen_ganancia": margen_ganancia,
                "lote": lote,
            }
        )

    if not detalles:
        raise ValueError("Debes agregar al menos un producto a la compra.")

    return detalles


def _productos_disponibles_para_devolucion(compra):
    cantidades_devueltas = {
        item["producto"]: item["total"] or 0
        for item in compra.devoluciones.values("producto").annotate(total=Sum("cantidad"))
    }
    productos = {}

    for detalle in compra.detalles.select_related("producto").all():
        item = productos.setdefault(
            detalle.producto_id,
            {
                "id": detalle.producto_id,
                "nombre": detalle.producto.nombre,
                "cantidad_comprada": 0,
            },
        )
        item["cantidad_comprada"] += detalle.cantidad

    disponibles = []
    for producto_id, item in productos.items():
        cantidad_disponible = item["cantidad_comprada"] - int(cantidades_devueltas.get(producto_id, 0))
        if cantidad_disponible > 0:
            disponibles.append(
                {
                    "id": item["id"],
                    "nombre": item["nombre"],
                    "cantidad_disponible": cantidad_disponible,
                }
            )

    disponibles.sort(key=lambda producto: producto["nombre"].lower())
    return disponibles


def _serializar_compras_para_devolucion(compras):
    return {
        str(compra.id): _productos_disponibles_para_devolucion(compra)
        for compra in compras
    }


def _render_devolucion_nueva(request, *, compras):
    return render(
        request,
        "inventario/dashboard/devoluciones/nueva.html",
        {
            "compras": compras,
            "data_compras": _serializar_compras_para_devolucion(compras),
        }
    )

@admin_required_session
def compra_lista(request):
    query = request.GET.get("q", "")
    estado_filtro = request.GET.get("estado", "")
    proveedor_id = request.GET.get("proveedor_id", "")
    fecha_inicio = request.GET.get("fecha_inicio", "")
    fecha_fin = request.GET.get("fecha_fin", "")
    
    compras = Compra.objects.select_related("proveedor").order_by("-fecha")
    
    if query:
        compras = compras.filter(
            Q(numero_factura__icontains=query) |
            Q(proveedor__nombre__icontains=query)
        )
    
    if proveedor_id:
        compras = compras.filter(proveedor_id=proveedor_id)
    
    filtro_fecha = Q()
    if fecha_inicio:
        try:
            filtro_fecha &= Q(fecha__gte=datetime.strptime(fecha_inicio, "%Y-%m-%d"))
        except ValueError:
            fecha_inicio = ""
    if fecha_fin:
        try:
            filtro_fecha &= Q(fecha__lte=datetime.strptime(fecha_fin, "%Y-%m-%d") + timedelta(days=1))
        except ValueError:
            fecha_fin = ""
    
    if filtro_fecha:
        compras = compras.filter(filtro_fecha)
    
    
    proveedores = Proveedor.objects.all()
    
    return render(request, "inventario/dashboard/compras/lista.html", {
        "compras": compras,
        "query": query,
        "estado_filtro": estado_filtro,
        "proveedor_id": proveedor_id,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "proveedores": proveedores
    })




@admin_required_session
def compra_nueva(request):
    if request.method == "POST":
        proveedor_id = request.POST.get("proveedor_id")
        proveedor = get_object_or_404(Proveedor, id=proveedor_id)

        numero_factura = request.POST.get("numero_factura", "").strip()
        if _compra_factura_duplicada(proveedor=proveedor, numero_factura=numero_factura):
            messages.error(request, "Ya existe esa factura para este proveedor.")

            proveedores = Proveedor.objects.all()
            productos = Producto.objects.filter(activo=True)

            return render(
                request,
                "inventario/dashboard/compras/nueva.html",
                {
                    "proveedores": proveedores,
                    "productos": productos
                }
            )

        try:
            detalles = _obtener_detalles_compra(request)
        except ValueError as exc:
            messages.error(request, str(exc))

            proveedores = Proveedor.objects.all()
            productos = Producto.objects.filter(activo=True)

            return render(
                request,
                "inventario/dashboard/compras/nueva.html",
                {
                    "proveedores": proveedores,
                    "productos": productos
                }
            )

        total = sum(
            (detalle["precio_compra"] * detalle["cantidad"] for detalle in detalles),
            Decimal("0"),
        )

        with transaction.atomic():
            compra = Compra.objects.create(
                proveedor=proveedor,
                total=total,
                numero_factura=numero_factura,
            )

            for detalle in detalles:
                DetalleCompra.objects.create(
                    compra=compra,
                    **detalle
                )

        return redirect("inventario:compra_detalle", compra.id)

    proveedores = Proveedor.objects.all()
    productos = Producto.objects.filter(activo=True)

    return render(
        request,
        "inventario/dashboard/compras/nueva.html",
        {
            "proveedores": proveedores,
            "productos": productos
        }
    )

@admin_required_session
def compra_detalle(request, compra_id):
    compra = get_object_or_404(Compra.objects.select_related("proveedor"), id=compra_id)
    detalles = compra.detalles.select_related("producto")
    devoluciones = compra.devoluciones.select_related("producto")
    return render(
        request,
        "inventario/dashboard/compras/detalle.html",
        {"compra": compra, "detalles": detalles, "devoluciones": devoluciones},
    )


@admin_required_session
def compra_editar(request, compra_id):

    compra = get_object_or_404(Compra, id=compra_id)

    if request.method == "POST":

        proveedor_id = request.POST.get("proveedor_id")
        compra.proveedor = get_object_or_404(Proveedor, id=proveedor_id)

        productos_ids = request.POST.getlist("productos_ids[]")
        cantidades = request.POST.getlist("cantidades[]")
        precios = request.POST.getlist("precios[]")
        impuestos = request.POST.getlist("impuestos[]")
        margenes = request.POST.getlist("margenes[]")

        total = Decimal("0")

        with transaction.atomic():

            compra.detalles.all().delete()

            for pid, c, p, i, m in zip(productos_ids, cantidades, precios, impuestos, margenes):

                if pid and c and p:
                    producto = get_object_or_404(Producto, id=pid)

                    c = int(c)
                    p = Decimal(p)
                    i = Decimal(i or 0)
                    m = Decimal(m or 0)

                    subtotal = c * p
                    total += subtotal

                    DetalleCompra.objects.create(
                        compra=compra,
                        producto=producto,
                        cantidad=c,
                        precio_compra=p,
                        impuesto=i,
                        margen_ganancia=m
                    )

            compra.total = total
            compra.save()

        return redirect("inventario:compra_detalle", compra.id)

    proveedores = Proveedor.objects.all()
    productos = Producto.objects.all()

    return render(request, "inventario/dashboard/compras/editar.html", {
        "compra": compra,
        "proveedores": proveedores,
        "productos": productos
    })

@admin_required_session
def compra_eliminar(request, compra_id):
    compra = get_object_or_404(Compra, id=compra_id)
    if request.method == "POST":
        for detalle in compra.detalles.all():
            producto = detalle.producto
            producto.stock -= detalle.cantidad
            producto.save()
        compra.delete()
    return redirect("inventario:compra_lista")


@admin_required_session
def devolucion_lista(request):
    estado_filtro = request.GET.get("estado", "")
    fecha_inicio = request.GET.get("fecha_inicio", "")
    fecha_fin = request.GET.get("fecha_fin", "")
    
    devoluciones = DevolucionCompra.objects.select_related("compra", "producto").order_by("-fecha")
    
    if estado_filtro:
        devoluciones = devoluciones.filter(estado=estado_filtro)
    
    filtro_fecha = Q()
    if fecha_inicio:
        try:
            filtro_fecha &= Q(fecha__gte=datetime.strptime(fecha_inicio, "%Y-%m-%d"))
        except ValueError:
            fecha_inicio = ""
    if fecha_fin:
        try:
            filtro_fecha &= Q(fecha__lte=datetime.strptime(fecha_fin, "%Y-%m-%d") + timedelta(days=1))
        except ValueError:
            fecha_fin = ""
    
    if filtro_fecha:
        devoluciones = devoluciones.filter(filtro_fecha)
    
    devoluciones_pendientes = DevolucionCompra.objects.filter(estado="pendiente").count()
    devoluciones_aprobadas = DevolucionCompra.objects.filter(estado="aprobada").count()
    devoluciones_rechazadas = DevolucionCompra.objects.filter(estado="rechazada").count()
    solicitudes_cliente = (
        SolicitudDevolucionVenta.objects
        .select_related("cliente", "detalle_venta__venta", "detalle_venta__producto")
        .order_by("-fecha_solicitud", "-id")
    )
    solicitudes_cliente_pendientes = solicitudes_cliente.filter(
        estado=SolicitudDevolucionVenta.ESTADO_PENDIENTE
    ).count()
    
    return render(request, "inventario/dashboard/devoluciones/lista.html", {
        "devoluciones": devoluciones,
        "estado_filtro": estado_filtro,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "devoluciones_pendientes": devoluciones_pendientes,
        "devoluciones_aprobadas": devoluciones_aprobadas,
        "devoluciones_rechazadas": devoluciones_rechazadas,
        "solicitudes_cliente": solicitudes_cliente,
        "solicitudes_cliente_pendientes": solicitudes_cliente_pendientes,
    })


@admin_required_session
def devolucion_nueva(request):
    compras = Compra.objects.select_related("proveedor").prefetch_related("detalles__producto", "devoluciones").all()

    if request.method == "POST":
        compra_id = request.POST.get("compra_id")
        producto_id = request.POST.get("producto_id")
        try:
            cantidad = _parse_positive_int(
                request.POST.get("cantidad") or 1,
                label="La cantidad a devolver",
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return _render_devolucion_nueva(request, compras=compras)

        motivo = request.POST.get("motivo", "")

        compra = get_object_or_404(
            Compra.objects.select_related("proveedor").prefetch_related("detalles__producto", "devoluciones"),
            id=compra_id,
        )
        productos_disponibles = {
            str(item["id"]): item
            for item in _productos_disponibles_para_devolucion(compra)
        }

        if not producto_id or producto_id not in productos_disponibles:
            messages.error(
                request,
                "Debes seleccionar un producto válido de la compra elegida.",
            )
            return _render_devolucion_nueva(request, compras=compras)

        producto = get_object_or_404(Producto, id=producto_id)
        producto_info = productos_disponibles[producto_id]

        if cantidad > producto_info["cantidad_disponible"]:
            messages.error(
                request,
                f"Solo puedes devolver {producto_info['cantidad_disponible']} unidad(es) de {producto.nombre} para esa compra.",
            )
            return _render_devolucion_nueva(request, compras=compras)

        stock_actual = Inventario.objects.filter(producto=producto).aggregate(total=Sum("stock"))["total"] or 0
        if cantidad > stock_actual:
            messages.error(
                request,
                f"No hay stock suficiente de {producto.nombre} para registrar esta devolución.",
            )
            return _render_devolucion_nueva(request, compras=compras)

        with transaction.atomic():
            devolucion = DevolucionCompra.objects.create(
                compra=compra,
                producto=producto,
                cantidad=cantidad,
                motivo=motivo,
            )

            inventarios = Inventario.objects.filter(producto=producto).order_by("fecha_ingreso")

            cantidad_restante = cantidad

            for inventario in inventarios:
                if cantidad_restante <= 0:
                    break

                if inventario.stock >= cantidad_restante:
                    inventario.stock -= cantidad_restante

                    MovimientoInventario.objects.create(
                        inventario=inventario,
                        producto=producto,
                        lote=inventario.lote,
                        cantidad=cantidad_restante,
                        tipo="DEVOLUCION"
                    )

                    inventario.save()
                    cantidad_restante = 0

                else:
                    cantidad_usada = inventario.stock

                    MovimientoInventario.objects.create(
                        inventario=inventario,
                        producto=producto,
                        lote=inventario.lote,
                        cantidad=cantidad_usada,
                        tipo="DEVOLUCION"
                    )

                    inventario.stock = 0
                    inventario.save()

                    cantidad_restante -= cantidad_usada

        return redirect("inventario:devolucion_lista")

    return _render_devolucion_nueva(request, compras=compras)

@admin_required_session
def devolucion_detalle(request, devolucion_id):
    devolucion = get_object_or_404(
        DevolucionCompra.objects.select_related("compra", "producto"), id=devolucion_id
    )
    return render(request, "inventario/dashboard/devoluciones/detalle.html", {"devolucion": devolucion})


@admin_required_session
def devolucion_eliminar(request, devolucion_id):
    devolucion = get_object_or_404(DevolucionCompra, id=devolucion_id)

    if request.method == "POST":
        producto = devolucion.producto
        cantidad = devolucion.cantidad

        inventarios = Inventario.objects.filter(producto=producto)

        for inventario in inventarios:
            if cantidad <= 0:
                break

            inventario.stock += cantidad

            MovimientoInventario.objects.create(
                inventario=inventario,
                producto=producto,
                lote=inventario.lote,
                cantidad=cantidad,
                tipo="INGRESO"
            )

            inventario.save()
            cantidad = 0

        devolucion.delete()

    return redirect("inventario:devolucion_lista")

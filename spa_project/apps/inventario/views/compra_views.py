from django.shortcuts import get_object_or_404, redirect, render
from apps.inventario.models import Compra, DetalleCompra, DevolucionCompra, Producto, Proveedor, Inventario, MovimientoInventario
from apps.sesiones.decorators import admin_required_session

from django.db.models import Case, IntegerField, Q, Value, When, Sum
from datetime import datetime, timedelta
from django.db import transaction
from decimal import Decimal, InvalidOperation
from django.contrib import messages
from django.core.exceptions import ValidationError
from apps.common.validation import validate_lote, validate_percentage
from apps.ventas.models import SolicitudDevolucionVenta

# =========================================================================
# FUNCIONES AUXILIARES DE PARSEO Y VALIDACIÓN
# =========================================================================

def _parse_positive_int(value, *, label):
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f"{label} debe ser un número entero válido.")
    if parsed <= 0:
        raise ValueError(f"{label} debe ser mayor a cero.")
    return parsed


def _parse_decimal(value, *, label, allow_zero=False):
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError, TypeError, ValueError):
        raise ValueError(f"{label} debe ser un número válido.")

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


def _parse_date_filter(value, *, label):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"{label} no es válida.") from exc


def _parse_optional_date(value, *, label):
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{label} no es valida.") from exc


def _producto_requiere(producto, nombre_especificacion):
    return any(
        spec.nombre == nombre_especificacion
        for spec in producto.especificaciones.all()
    )


def _productos_para_formulario_compra():
    productos = Producto.objects.filter(activo=True).prefetch_related("especificaciones")
    for producto in productos:
        producto.requiere_vencimiento = _producto_requiere(producto, "fecha_vencimiento")
        producto.requiere_pao = _producto_requiere(producto, "pao")
    return productos


def _aplicar_rango_fechas(queryset, *, fecha_inicio, fecha_fin, field_name):
    inicio = _parse_date_filter(fecha_inicio, label="La fecha de inicio")
    fin = _parse_date_filter(fecha_fin, label="La fecha de fin")
    if inicio and fin and inicio > fin:
        raise ValueError("La fecha de inicio no puede ser posterior a la fecha de fin.")
    if inicio:
        queryset = queryset.filter(**{f"{field_name}__gte": inicio})
    if fin:
        queryset = queryset.filter(**{f"{field_name}__lte": fin + timedelta(days=1)})
    return queryset


def _obtener_detalles_compra(request):
    productos_ids = request.POST.getlist("productos_ids[]")
    cantidades = request.POST.getlist("cantidades[]")
    precios = request.POST.getlist("precios[]")
    impuestos = request.POST.getlist("impuestos[]")
    margenes = request.POST.getlist("margenes[]")
    lotes = request.POST.getlist("lotes[]")
    fechas_vencimiento = request.POST.getlist("fechas_vencimiento[]")
    paos = request.POST.getlist("paos[]")

    total_filas = max(
        len(productos_ids), len(cantidades), len(precios),
        len(impuestos), len(margenes), len(lotes),
        len(fechas_vencimiento), len(paos), 0
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
        fecha_vencimiento = (fechas_vencimiento[index] if index < len(fechas_vencimiento) else "")
        pao = (paos[index] if index < len(paos) else "").strip()

        if not any([producto_id, cantidad_raw, precio_raw, impuesto_raw, margen_raw, lote]):
            continue

        fila = index + 1

        if not producto_id:
            raise ValueError(f"Debes seleccionar un producto en la fila {fila}.")

        producto = (
            Producto.objects.filter(id=producto_id, activo=True)
            .prefetch_related("especificaciones")
            .first()
        )
        if not producto:
            raise ValueError(f"El producto de la fila {fila} no es válido.")

        cantidad = _parse_positive_int(cantidad_raw, label=f"La cantidad de la fila {fila}")
        precio_compra = _parse_decimal(precio_raw, label=f"El precio de la fila {fila}")
        impuesto = validate_percentage(impuesto_raw or "0", label=f"El impuesto de la fila {fila}")
        margen_ganancia = validate_percentage(margen_raw or "0", label=f"El margen de la fila {fila}")
        lote = validate_lote(lote, label=f"El lote de la fila {fila}")
        requiere_vencimiento = _producto_requiere(producto, "fecha_vencimiento")
        requiere_pao = _producto_requiere(producto, "pao")
        fecha_vencimiento = (
            _parse_optional_date(fecha_vencimiento, label=f"La fecha de vencimiento de la fila {fila}")
            if requiere_vencimiento
            else None
        )
        pao = pao if requiere_pao else None

        duplicate_key = (producto.id, lote.casefold())
        if duplicate_key in filas_duplicadas:
            raise ValueError(f"El producto {producto.nombre} con lote {lote} está repetido en la compra.")

        filas_duplicadas.add(duplicate_key)

        detalles.append({
            "producto": producto,
            "cantidad": cantidad,
            "precio_compra": precio_compra,
            "impuesto": impuesto,
            "margen_ganancia": margen_ganancia,
            "lote": lote,
            "fecha_vencimiento": fecha_vencimiento,
            "pao": pao,
        })

    if not detalles:
        raise ValueError("Debes agregar al menos un producto a la compra.")

    return detalles

# =========================================================================
# VISTAS DE COMPRAS
# =========================================================================

@admin_required_session
def compra_lista(request):
    query = request.GET.get("q", "")
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
    
    try:
        compras = _aplicar_rango_fechas(compras, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin, field_name="fecha")
    except ValueError as exc:
        messages.error(request, str(exc))
        fecha_inicio = ""
        fecha_fin = ""
    
    proveedores = Proveedor.objects.all()
    return render(request, "inventario/dashboard/compras/lista.html", {
        "compras": compras,
        "query": query,
        "proveedor_id": proveedor_id,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "proveedores": proveedores
    })


@admin_required_session
def compra_nueva(request):
    if request.method == "POST":
        proveedor_id = request.POST.get("proveedor_id")
        numero_factura = request.POST.get("numero_factura", "").strip()
        observaciones = request.POST.get("observaciones", "").strip()

        if not proveedor_id:
            messages.error(request, "Debes seleccionar un proveedor.")
            return redirect("inventario:compra_nueva")

        proveedor = get_object_or_404(Proveedor, id=proveedor_id)

        if _compra_factura_duplicada(proveedor=proveedor, numero_factura=numero_factura):
            messages.error(request, "Ya existe esa factura para este proveedor.")
            return render(request, "inventario/dashboard/compras/nueva.html", {
                "proveedores": Proveedor.objects.all(),
                "productos": _productos_para_formulario_compra(),
            })

        try:
            detalles = _obtener_detalles_compra(request)
            total = sum((d["precio_compra"] * d["cantidad"] for d in detalles), Decimal("0"))

            with transaction.atomic():
                compra = Compra.objects.create(
                    proveedor=proveedor,
                    total=total,
                    numero_factura=numero_factura,
                    observaciones=observaciones
                )
                for detalle in detalles:
                    # El .save() del modelo maneja el Inventario de forma limpia
                    DetalleCompra.objects.create(compra=compra, **detalle)

            messages.success(request, "Compra registrada exitosamente.")
            return redirect("inventario:compra_detalle", compra.id)

        except (ValueError, ValidationError) as exc:
            # Captura tanto errores de parseo como las validaciones clean() del modelo
            if isinstance(exc, ValidationError):
                messages.error(request, f"Error de validación en los productos: {exc.messages}")
            else:
                messages.error(request, str(exc))

    proveedores = Proveedor.objects.all()
    productos = _productos_para_formulario_compra()
    return render(request, "inventario/dashboard/compras/nueva.html", {
        "proveedores": proveedores,
        "productos": productos,
    })


@admin_required_session
def compra_detalle(request, compra_id):
    compra = get_object_or_404(Compra.objects.select_related("proveedor"), id=compra_id)
    detalles = compra.detalles.select_related("producto")
    devoluciones = compra.devoluciones.select_related("producto")
    return render(request, "inventario/dashboard/compras/detalle.html", {
        "compra": compra, "detalles": detalles, "devoluciones": devoluciones
    })


@admin_required_session
def compra_editar(request, compra_id):
    """
    Modificar una compra requiere revertir el inventario ingresado originalmente 
    para evitar inconsistencias o duplicidad de stock.
    """
    compra = get_object_or_404(Compra, id=compra_id)

    if request.method == "POST":
        proveedor_id = request.POST.get("proveedor_id")
        numero_factura = request.POST.get("numero_factura", "").strip()
        observaciones = request.POST.get("observaciones", "").strip()
        
        proveedor = get_object_or_404(Proveedor, id=proveedor_id)

        if _compra_factura_duplicada(proveedor=proveedor, numero_factura=numero_factura, exclude_id=compra.id):
            messages.error(request, "Ya existe esa factura para este proveedor.")
            return redirect("inventario:compra_editar", compra.id)

        try:
            detalles_nuevos = _obtener_detalles_compra(request)
            total = sum((d["precio_compra"] * d["cantidad"] for d in detalles_nuevos), Decimal("0"))

            with transaction.atomic():
                # 1. Revertir el Inventario y Movimientos de los detalles anteriores antes de borrarlos
                for det_antiguo in compra.detalles.all():
                    inv = Inventario.objects.filter(producto=det_antiguo.producto, lote=det_antiguo.lote).first()
                    if inv:
                        inv.stock -= det_antiguo.cantidad
                        inv.save()
                        MovimientoInventario.objects.create(
                            inventario=inv, producto=det_antiguo.producto, lote=det_antiguo.lote,
                            cantidad=det_antiguo.cantidad, tipo="SALIDA" # Corrección/Ajuste por edición
                        )
                
                # 2. Eliminar detalles antiguos
                compra.detalles.all().delete()

                # 3. Actualizar la cabecera de la compra
                compra.proveedor = proveedor
                compra.numero_factura = numero_factura
                compra.observaciones = observaciones
                compra.total = total
                compra.save()

                # 4. Crear los nuevos detalles (quienes volverán a sumar al Inventario mediante su model save)
                for detalle in detalles_nuevos:
                    DetalleCompra.objects.create(compra=compra, **detalle)

            messages.success(request, "Compra actualizada correctamente.")
            return redirect("inventario:compra_detalle", compra.id)

        except (ValueError, ValidationError) as exc:
            if isinstance(exc, ValidationError):
                messages.error(request, f"Error en especificaciones del modelo: {exc.messages}")
            else:
                messages.error(request, str(exc))

    proveedores = Proveedor.objects.all()
    productos = Producto.objects.filter(activo=True).prefetch_related("especificaciones")
    return render(request, "inventario/dashboard/compras/editar.html", {
        "compra": compra,
        "proveedores": proveedores,
        "productos": productos
    })


@admin_required_session
def compra_eliminar(request, compra_id):
    compra = get_object_or_404(Compra, id=compra_id)
    if request.method == "POST":
        try:
            with transaction.atomic():
                for detalle in compra.detalles.all():
                    # Corrección: El stock se descuenta de INVENTARIO (por producto y lote), no de Producto.
                    inventario = Inventario.objects.filter(producto=detalle.producto, lote=detalle.lote).first()
                    if inventario:
                        if inventario.stock < detalle.cantidad:
                            raise ValidationError(f"No se puede eliminar la compra. El producto {detalle.producto.nombre} ya tiene movimientos y el stock actual en el lote {detalle.lote} es insuficiente.")
                        
                        inventario.stock -= detalle.cantidad
                        inventario.save()
                        
                        MovimientoInventario.objects.create(
                            inventario=inventario,
                            producto=detalle.producto,
                            lote=detalle.lote,
                            cantidad=detalle.cantidad,
                            tipo="SALIDA"
                        )
                compra.delete()
            messages.success(request, "Compra eliminada y stock revertido con éxito.")
        except ValidationError as e:
            messages.error(request, str(e.message))
            return redirect("inventario:compra_detalle", compra.id)
            
    return redirect("inventario:compra_lista")

# =========================================================================
# VISTAS DE DEVOLUCIONES
# =========================================================================

def _productos_disponibles_para_devolucion(compra):
    # Calcula cuántas unidades de cada producto ya han sido devueltas en esta compra
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
                "lote": detalle.lote,  # Importante trackear el lote de la compra
                "cantidad_comprada": 0,
            },
        )
        item["cantidad_comprada"] += detalle.cantidad

    disponibles = []
    for producto_id, item in productos.items():
        cantidad_disponible = item["cantidad_comprada"] - int(cantidades_devueltas.get(producto_id, 0))
        if cantidad_disponible > 0:
            disponibles.append({
                "id": item["id"],
                "nombre": item["nombre"],
                "lote": item["lote"],
                "cantidad_disponible": cantidad_disponible,
            })

    disponibles.sort(key=lambda p: p["nombre"].lower())
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
def devolucion_lista(request):
    estado_filtro = request.GET.get("estado", "")
    fecha_inicio = request.GET.get("fecha_inicio", "")
    fecha_fin = request.GET.get("fecha_fin", "")
    
    prioridad_estado = Case(
        When(estado="pendiente", then=Value(0)),
        When(estado="en_proceso", then=Value(1)),
        When(estado="aprobada", then=Value(2)),
        When(estado="rechazada", then=Value(3)),
        default=Value(4),
        output_field=IntegerField(),
    )
    devoluciones = DevolucionCompra.objects.select_related("compra", "producto").order_by(prioridad_estado, "-fecha")
    
    if estado_filtro:
        devoluciones = devoluciones.filter(estado=estado_filtro)
    
    try:
        devoluciones = _aplicar_rango_fechas(devoluciones, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin, field_name="fecha")
    except ValueError as exc:
        messages.error(request, str(exc))
        fecha_inicio = ""
        fecha_fin = ""
    
    return render(request, "inventario/dashboard/devoluciones/lista.html", {
        "devoluciones": devoluciones,
        "estado_filtro": estado_filtro,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "devoluciones_pendientes": DevolucionCompra.objects.filter(estado="pendiente").count(),
        "devoluciones_aprobadas": DevolucionCompra.objects.filter(estado="aprobada").count(),
        "devoluciones_rechazadas": DevolucionCompra.objects.filter(estado="rechazada").count(),
    })


@admin_required_session
def devolucion_nueva(request):
    compras = Compra.objects.select_related("proveedor").prefetch_related("detalles__producto", "devoluciones").all()

    if request.method == "POST":
        compra_id = request.POST.get("compra_id")
        producto_id = request.POST.get("producto_id")
        motivo = request.POST.get("motivo", "").strip()

        try:
            cantidad = _parse_positive_int(request.POST.get("cantidad") or 1, label="La cantidad a devolver")
        except ValueError as exc:
            messages.error(request, str(exc))
            return _render_devolucion_nueva(request, compras=compras)

        compra = get_object_or_404(Compra, id=compra_id)
        productos_disponibles = {str(item["id"]): item for item in _productos_disponibles_para_devolucion(compra)}

        if not producto_id or producto_id not in productos_disponibles:
            messages.error(request, "Debes seleccionar un producto válido de la compra elegida.")
            return _render_devolucion_nueva(request, compras=compras)

        producto = get_object_or_404(Producto, id=producto_id)
        producto_info = productos_disponibles[producto_id]
        lote_compra = producto_info["lote"]

        if cantidad > producto_info["cantidad_disponible"]:
            messages.error(request, f"Solo puedes devolver {producto_info['cantidad_disponible']} unidad(es).")
            return _render_devolucion_nueva(request, compras=compras)

        # Buscar el inventario específico ligado a ese producto y lote de la compra original
        inventario = Inventario.objects.filter(producto=producto, lote=lote_compra).first()

        if not inventario or inventario.stock < cantidad:
            messages.error(request, f"No hay stock suficiente en el lote '{lote_compra}' para realizar la devolución.")
            return _render_devolucion_nueva(request, compras=compras)

        with transaction.atomic():
            DevolucionCompra.objects.create(
                compra=compra,
                producto=producto,
                cantidad=cantidad,
                motivo=motivo,
                estado="aprobada"  # O "pendiente" según las políticas del negocio
            )

            # Descontar del lote correcto
            inventario.stock -= cantidad
            inventario.save()

            MovimientoInventario.objects.create(
                inventario=inventario,
                producto=producto,
                lote=lote_compra,
                cantidad=cantidad,
                tipo="DEVOLUCION"
            )

        messages.success(request, "Devolución registrada exitosamente.")
        return redirect("inventario:devolucion_lista")

    return _render_devolucion_nueva(request, compras=compras)


@admin_required_session
def devolucion_detalle(request, devolucion_id):
    devolucion = get_object_or_404(DevolucionCompra.objects.select_related("compra", "producto"), id=devolucion_id)
    return render(request, "inventario/dashboard/devoluciones/detalle.html", {"devolucion": devolucion})


@admin_required_session
def devolucion_eliminar(request, devolucion_id):
    devolucion = get_object_or_404(DevolucionCompra, id=devolucion_id)

    if request.method == "POST":
        with transaction.atomic():
            # Buscar el lote original usando la relación de la compra de la que provino la devolución
            detalle_orig = DetalleCompra.objects.filter(compra=devolucion.compra, producto=devolucion.producto).first()
            lote_objetivo = detalle_orig.lote if detalle_orig else "S/L"

            inventario, _ = Inventario.objects.get_or_create(
                producto=devolucion.producto,
                lote=lote_objetivo,
                defaults={"stock": 0, "precio_venta": devolucion.producto.precio_venta}
            )
            
            inventario.stock += devolucion.cantidad
            inventario.save()

            MovimientoInventario.objects.create(
                inventario=inventario,
                producto=devolucion.producto,
                lote=lote_objetivo,
                cantidad=devolucion.cantidad,
                tipo="INGRESO"
            )
            devolucion.delete()

        messages.success(request, "Devolución eliminada. El stock fue reintegrado al lote correspondiente.")
    return redirect("inventario:devolucion_lista")

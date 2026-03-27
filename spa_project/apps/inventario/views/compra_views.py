from datetime import datetime, timedelta

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.common.currency import parse_money
from apps.inventario.models import Compra, DetalleCompra, DevolucionCompra, Producto, Proveedor
from apps.inventario.services import descontar_stock, generar_lote_default, registrar_ingreso
from apps.sesiones.decorators import admin_required_session


@admin_required_session
def compra_lista(request):
    query = request.GET.get("q", "")
    estado_filtro = request.GET.get("estado", "")
    proveedor_id = request.GET.get("proveedor_id", "")
    fecha_inicio = request.GET.get("fecha_inicio", "")
    fecha_fin = request.GET.get("fecha_fin", "")

    compras = Compra.objects.select_related("proveedor").order_by("-fecha")

    if query:
        compras = compras.filter(numero_factura__icontains=query)

    if estado_filtro and estado_filtro != "completada":
        compras = compras.none()

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

    compras_completadas = Compra.objects.count()
    compras_pendientes = 0
    compras_canceladas = 0
    proveedores = Proveedor.objects.all()

    return render(
        request,
        "inventario/dashboard/compras/lista.html",
        {
            "compras": compras,
            "query": query,
            "estado_filtro": estado_filtro,
            "proveedor_id": proveedor_id,
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
            "proveedores": proveedores,
            "compras_completadas": compras_completadas,
            "compras_pendientes": compras_pendientes,
            "compras_canceladas": compras_canceladas,
        },
    )


@admin_required_session
def compra_nueva(request):
    if request.method == "POST":
        proveedor_id = request.POST.get("proveedor_id")
        proveedor = get_object_or_404(Proveedor, id=proveedor_id)
        numero_factura = request.POST.get("numero_factura", "")
        total = parse_money(request.POST.get("total"))

        productos_ids = request.POST.getlist("productos_ids[]")
        cantidades = request.POST.getlist("cantidades[]")
        precios = request.POST.getlist("precios[]")
        lotes = request.POST.getlist("lotes[]")

        with transaction.atomic():
            compra = Compra.objects.create(
                proveedor=proveedor,
                total=total,
                numero_factura=numero_factura,
            )

            for index, (producto_id, cantidad, precio) in enumerate(
                zip(productos_ids, cantidades, precios)
            ):
                if not (producto_id and cantidad and precio):
                    continue

                producto = get_object_or_404(Producto, id=producto_id)
                cantidad_int = int(cantidad)
                lote = ""
                if index < len(lotes):
                    lote = (lotes[index] or "").strip()
                if not lote:
                    lote = generar_lote_default(producto.id, prefix=f"COMPRA-{compra.id}")

                detalle, created = DetalleCompra.objects.get_or_create(
                    compra=compra,
                    producto=producto,
                    lote=lote,
                    defaults={
                        "cantidad": cantidad_int,
                        "precio_compra": parse_money(precio),
                    },
                )
                if not created:
                    detalle.cantidad += cantidad_int
                    detalle.precio_compra = parse_money(precio)
                    detalle.save(update_fields=["cantidad", "precio_compra"])

                registrar_ingreso(
                    producto,
                    cantidad_int,
                    lote=lote,
                    fecha_ingreso=compra.fecha,
                )

        return redirect("inventario:compra_detalle", compra_id=compra.id)

    proveedores = Proveedor.objects.all()
    productos = Producto.objects.all()
    return render(
        request,
        "inventario/dashboard/compras/nueva.html",
        {"proveedores": proveedores, "productos": productos},
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
        compra.numero_factura = request.POST.get("numero_factura", "")
        compra.total = parse_money(request.POST.get("total"))
        compra.save()
        return redirect("inventario:compra_detalle", compra_id=compra.id)

    proveedores = Proveedor.objects.all()
    return render(
        request,
        "inventario/dashboard/compras/editar.html",
        {"compra": compra, "proveedores": proveedores},
    )


@admin_required_session
def compra_eliminar(request, compra_id):
    compra = get_object_or_404(Compra, id=compra_id)
    if request.method == "POST":
        try:
            with transaction.atomic():
                for detalle in compra.detalles.select_related("producto"):
                    descontar_stock(
                        detalle.producto,
                        detalle.cantidad,
                        lote=detalle.lote or None,
                    )
                compra.delete()
        except ValueError as exc:
            messages.error(
                request,
                f"No se pudo eliminar la compra porque el stock actual ya no cubre sus lotes: {exc}",
            )
            return redirect("inventario:compra_detalle", compra_id=compra.id)

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

    return render(
        request,
        "inventario/dashboard/devoluciones/lista.html",
        {
            "devoluciones": devoluciones,
            "estado_filtro": estado_filtro,
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
            "devoluciones_pendientes": devoluciones_pendientes,
            "devoluciones_aprobadas": devoluciones_aprobadas,
            "devoluciones_rechazadas": devoluciones_rechazadas,
        },
    )


@admin_required_session
def devolucion_nueva(request):
    if request.method == "POST":
        compra_id = request.POST.get("compra_id")
        producto_id = request.POST.get("producto_id")
        cantidad = int(request.POST.get("cantidad") or 1)
        motivo = request.POST.get("motivo", "")

        compra = get_object_or_404(Compra, id=compra_id)
        producto = get_object_or_404(Producto, id=producto_id)
        detalle = compra.detalles.filter(producto_id=producto_id).order_by("id").first()
        lote = detalle.lote if detalle and detalle.lote else None

        try:
            with transaction.atomic():
                descontar_stock(producto, cantidad, lote=lote)
                DevolucionCompra.objects.create(
                    compra=compra,
                    producto=producto,
                    cantidad=cantidad,
                    motivo=motivo,
                )
        except ValueError as exc:
            messages.error(request, f"No hay stock suficiente para registrar la devolucion: {exc}")
            return redirect("inventario:devolucion_nueva")

        return redirect("inventario:devolucion_lista")

    compras = Compra.objects.select_related("proveedor").all()
    return render(request, "inventario/dashboard/devoluciones/nueva.html", {"compras": compras})


@admin_required_session
def devolucion_detalle(request, devolucion_id):
    devolucion = get_object_or_404(
        DevolucionCompra.objects.select_related("compra", "producto"),
        id=devolucion_id,
    )
    return render(
        request,
        "inventario/dashboard/devoluciones/detalle.html",
        {"devolucion": devolucion},
    )


@admin_required_session
def devolucion_eliminar(request, devolucion_id):
    devolucion = get_object_or_404(DevolucionCompra, id=devolucion_id)
    if request.method == "POST":
        detalle = (
            devolucion.compra.detalles.filter(producto_id=devolucion.producto_id)
            .order_by("id")
            .first()
        )
        registrar_ingreso(
            devolucion.producto,
            devolucion.cantidad,
            lote=detalle.lote if detalle and detalle.lote else None,
            fecha_ingreso=devolucion.compra.fecha,
        )
        devolucion.delete()
    return redirect("inventario:devolucion_lista")

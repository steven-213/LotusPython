from django.shortcuts import get_object_or_404, redirect, render

from apps.inventario.models import Compra, DetalleCompra, DevolucionCompra, Producto, Proveedor
from apps.sesiones.decorators import admin_required_session


from django.shortcuts import get_object_or_404, redirect, render
from django.db.models import Q, Sum
from datetime import datetime, timedelta

from apps.inventario.models import Compra, DetalleCompra, DevolucionCompra, Producto, Proveedor
from apps.sesiones.decorators import admin_required_session


@admin_required_session
def compra_lista(request):
    query = request.GET.get("q", "")
    estado_filtro = request.GET.get("estado", "")
    proveedor_id = request.GET.get("proveedor_id", "")
    fecha_inicio = request.GET.get("fecha_inicio", "")
    fecha_fin = request.GET.get("fecha_fin", "")
    
    compras = Compra.objects.select_related("proveedor").order_by("-fecha")
    
    # Filtro por búsqueda (número de factura)
    if query:
        compras = compras.filter(numero_factura__icontains=query)
    
    # Filtro por estado
    if estado_filtro:
        compras = compras.filter(estado=estado_filtro)
    
    # Filtro por proveedor
    if proveedor_id:
        compras = compras.filter(proveedor_id=proveedor_id)
    
    # Filtro por rango de fechas
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
    
    # Contar por estado
    compras_completadas = Compra.objects.filter(estado="completada").count()
    compras_pendientes = Compra.objects.filter(estado="pendiente").count()
    compras_canceladas = Compra.objects.filter(estado="cancelada").count()
    
    # Obtener proveedores para el filtro
    proveedores = Proveedor.objects.all()
    
    return render(request, "inventario/compras/lista.html", {
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
    })


@admin_required_session
def compra_nueva(request):
    if request.method == "POST":
        proveedor_id = request.POST.get("proveedor_id")
        proveedor = get_object_or_404(Proveedor, id=proveedor_id)
        numero_factura = request.POST.get("numero_factura", "")
        total = request.POST.get("total") or 0
        
        compra = Compra.objects.create(
            proveedor=proveedor,
            total=total,
            numero_factura=numero_factura,
        )
        
        # Agregar detalles de compra
        productos_ids = request.POST.getlist("productos_ids[]")
        cantidades = request.POST.getlist("cantidades[]")
        precios = request.POST.getlist("precios[]")
        
        for producto_id, cantidad, precio in zip(productos_ids, cantidades, precios):
            if producto_id and cantidad and precio:
                producto = get_object_or_404(Producto, id=producto_id)
                DetalleCompra.objects.create(
                    compra=compra,
                    producto=producto,
                    cantidad=int(cantidad),
                    precio_compra=float(precio),
                )
                # Actualizar stock del producto
                producto.stock += int(cantidad)
                producto.save()
        
        return redirect("inventario:compra_detalle", compra_id=compra.id)
    
    proveedores = Proveedor.objects.all()
    productos = Producto.objects.all()
    return render(
        request,
        "inventario/compras/nueva.html",
        {"proveedores": proveedores, "productos": productos},
    )


@admin_required_session
def compra_detalle(request, compra_id):
    compra = get_object_or_404(Compra.objects.select_related("proveedor"), id=compra_id)
    detalles = compra.detalles.select_related("producto")
    devoluciones = compra.devoluciones.select_related("producto")
    return render(
        request,
        "inventario/compras/detalle.html",
        {"compra": compra, "detalles": detalles, "devoluciones": devoluciones},
    )


@admin_required_session
def compra_editar(request, compra_id):
    compra = get_object_or_404(Compra, id=compra_id)
    if request.method == "POST":
        proveedor_id = request.POST.get("proveedor_id")
        compra.proveedor = get_object_or_404(Proveedor, id=proveedor_id)
        compra.numero_factura = request.POST.get("numero_factura", "")
        compra.total = request.POST.get("total") or 0
        compra.save()
        return redirect("inventario:compra_detalle", compra_id=compra.id)
    
    proveedores = Proveedor.objects.all()
    return render(
        request,
        "inventario/compras/editar.html",
        {"compra": compra, "proveedores": proveedores},
    )


@admin_required_session
def compra_eliminar(request, compra_id):
    compra = get_object_or_404(Compra, id=compra_id)
    if request.method == "POST":
        # Restaurar stock de productos
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
    
    # Filtro por estado
    if estado_filtro:
        devoluciones = devoluciones.filter(estado=estado_filtro)
    
    # Filtro por rango de fechas
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
    
    # Contar por estado
    devoluciones_pendientes = DevolucionCompra.objects.filter(estado="pendiente").count()
    devoluciones_aprobadas = DevolucionCompra.objects.filter(estado="aprobada").count()
    devoluciones_rechazadas = DevolucionCompra.objects.filter(estado="rechazada").count()
    
    return render(request, "inventario/devoluciones/lista.html", {
        "devoluciones": devoluciones,
        "estado_filtro": estado_filtro,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "devoluciones_pendientes": devoluciones_pendientes,
        "devoluciones_aprobadas": devoluciones_aprobadas,
        "devoluciones_rechazadas": devoluciones_rechazadas,
    })


@admin_required_session
def devolucion_nueva(request):
    if request.method == "POST":
        compra_id = request.POST.get("compra_id")
        producto_id = request.POST.get("producto_id")
        cantidad = int(request.POST.get("cantidad") or 1)
        motivo = request.POST.get("motivo", "")
        
        compra = get_object_or_404(Compra, id=compra_id)
        producto = get_object_or_404(Producto, id=producto_id)
        
        DevolucionCompra.objects.create(
            compra=compra,
            producto=producto,
            cantidad=cantidad,
            motivo=motivo,
        )
        
        # Reducir stock del producto
        producto.stock -= cantidad
        producto.save()
        
        return redirect("inventario:devolucion_lista")
    
    compras = Compra.objects.select_related("proveedor").all()
    return render(request, "inventario/devoluciones/nueva.html", {"compras": compras})


@admin_required_session
def devolucion_detalle(request, devolucion_id):
    devolucion = get_object_or_404(
        DevolucionCompra.objects.select_related("compra", "producto"), id=devolucion_id
    )
    return render(request, "inventario/devoluciones/detalle.html", {"devolucion": devolucion})


@admin_required_session
def devolucion_eliminar(request, devolucion_id):
    devolucion = get_object_or_404(DevolucionCompra, id=devolucion_id)
    if request.method == "POST":
        # Restaurar stock del producto
        producto = devolucion.producto
        producto.stock += devolucion.cantidad
        producto.save()
        devolucion.delete()
    return redirect("inventario:devolucion_lista")

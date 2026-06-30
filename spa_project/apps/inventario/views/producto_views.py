import csv
import io
import json
from decimal import Decimal, InvalidOperation
from hashlib import md5
from types import SimpleNamespace

from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import IntegerField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone  # CORRECCIÓN: Importación necesaria para MovimientoInventario

from apps.common.seo import apply_public_page_cache_headers, serialize_structured_data
from apps.inventario.models import CategoriaProducto, Producto, Proveedor, Inventario, MovimientoInventario
from apps.inventario.services import (
    anotar_stock_disponible,
    obtener_stock_disponible,
    queryset_productos_basico,
)
from apps.inventario.storage import subir_imagen_producto

from apps.sesiones.decorators import admin_required_session, login_required_session
from apps.sesiones.models import Usuario

from apps.ventas.models import DetalleVenta, ValidacionVenta, Venta
from apps.ventas.telegram_notifier import notificar_compra_pendiente


PUBLIC_PRODUCTS_CACHE_TIMEOUT = getattr(settings, "PUBLIC_CATALOG_CACHE_TIMEOUT", 60)
PUBLIC_PRODUCTS_CACHE_VERSION_KEY = "public:productos:version"
CSV_PRODUCT_COLUMN_ALIASES = {
    "nombre": {"nombre", "name", "producto"},
    "descripcion": {"descripcion", "description", "detalle"},
    "precio_compra": {"precio_compra", "precio", "compra", "costo", "cost"},
    "proveedor": {"proveedor", "supplier"},
    "impuesto": {"impuesto", "iva", "tax"},
    "margen_ganancia": {"margen_ganancia", "margen", "margin"},
    "imagen": {"imagen", "image", "imagen_url"},
}
DEFAULT_PRODUCT_CATEGORY_NAME = "Sin categoria"


def _parse_decimal_csv(valor, etiqueta):
    texto = str(valor or "").strip().replace("$", "").replace(" ", "")

    if not texto:
        raise ValueError(f"{etiqueta} vacío")

    if "," in texto and "." in texto:
        if texto.rfind(",") > texto.rfind("."):
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", "")
    elif "," in texto:
        texto = texto.replace(".", "").replace(",", ".")

    try:
        return Decimal(texto)
    except InvalidOperation as exc:
        raise ValueError(f"{etiqueta} inválido") from exc


def _calcular_precio_venta(precio_compra, impuesto, margen_ganancia):
    impuesto_valor = precio_compra * (impuesto / Decimal("100"))
    margen_valor = precio_compra * (margen_ganancia / Decimal("100"))
    return (precio_compra + impuesto_valor + margen_valor).quantize(Decimal("0.01"))


def _categoria_producto_default():
    categoria, _created = CategoriaProducto.objects.get_or_create(
        nombre=DEFAULT_PRODUCT_CATEGORY_NAME,
        defaults={"activo": True},
    )
    return categoria


def _categorias_producto_activas():
    return CategoriaProducto.objects.filter(activo=True).order_by("nombre")


def _render_producto_form(request, producto=None):
    return render(
        request,
        "inventario/dashboard/productos/form.html",
        {
            "producto": producto,
            "proveedores": Proveedor.objects.all().order_by("nombre"),
            "categorias": _categorias_producto_activas(),
        },
    )


def _parse_decimal_form(request, campo, default, etiqueta):
    raw_value = request.POST.get(campo)
    value = raw_value if raw_value not in (None, "") else default

    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        messages.error(request, f"{etiqueta} debe ser un numero valido.")
        return None


def _resolver_proveedor_form(request):
    proveedor_id = request.POST.get("proveedor_id")
    if not proveedor_id:
        messages.error(request, "El proveedor es obligatorio.")
        return None

    proveedor = Proveedor.objects.filter(id=proveedor_id, activo=True).first()
    if proveedor is None:
        messages.error(request, "Selecciona un proveedor valido.")
    return proveedor


def _resolver_categoria_form(request):
    categoria_id = request.POST.get("categoria_id")
    if not categoria_id:
        messages.error(request, "La categoria es obligatoria.")
        return None

    categoria = CategoriaProducto.objects.filter(id=categoria_id, activo=True).first()
    if categoria is None:
        messages.error(request, "Selecciona una categoria valida.")
    return categoria


def _detectar_delimitador_csv(contenido):
    muestra = contenido[:1024]

    try:
        return csv.Sniffer().sniff(muestra, delimiters=",;\t").delimiter
    except csv.Error:
        return ";" if muestra.count(";") > muestra.count(",") else ","


def _mapear_encabezados_productos(encabezados):
    mapping = {}

    for index, encabezado in enumerate(encabezados):
        normalizado = str(encabezado or "").strip().lower()

        for campo, aliases in CSV_PRODUCT_COLUMN_ALIASES.items():
            if normalizado in aliases and campo not in mapping:
                mapping[campo] = index

    return mapping


def _leer_productos_desde_csv(archivo_csv):
    if not archivo_csv:
        raise ValueError("Selecciona un archivo CSV para importar.")

    if not archivo_csv.name.lower().endswith(".csv"):
        raise ValueError("El archivo debe tener extensión .csv.")

    contenido_bytes = archivo_csv.read()

    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            contenido = contenido_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            contenido = None

    if contenido is None or not contenido.strip():
        raise ValueError("No se pudo leer el archivo CSV o está vacío.")

    lector = csv.reader(
        io.StringIO(contenido),
        delimiter=_detectar_delimitador_csv(contenido),
    )
    filas = [fila for fila in lector if any(str(celda).strip() for celda in fila)]

    if not filas:
        raise ValueError("El archivo CSV no contiene filas para importar.")

    encabezados = _mapear_encabezados_productos(filas[0])
    tiene_encabezados = "nombre" in encabezados and "precio_compra" in encabezados
    filas_datos = filas[1:] if tiene_encabezados else filas
    inicio_linea = 2 if tiene_encabezados else 1

    if not filas_datos:
        raise ValueError("El archivo CSV no contiene productos después del encabezado.")

    productos = []

    for numero_linea, fila in enumerate(filas_datos, start=inicio_linea):
        if tiene_encabezados:
            def obtener(campo):
                index = encabezados.get(campo)
                if index is None or len(fila) <= index:
                    return ""
                return fila[index]

            productos.append(
                {
                    "linea": numero_linea,
                    "nombre": str(obtener("nombre")).strip(),
                    "descripcion": str(obtener("descripcion")).strip(),
                    "precio_compra": str(obtener("precio_compra")).strip(),
                    "proveedor": str(obtener("proveedor")).strip(),
                    "impuesto": str(obtener("impuesto")).strip(),
                    "margen_ganancia": str(obtener("margen_ganancia")).strip(),
                    "imagen": str(obtener("imagen")).strip(),
                }
            )
        else:
            productos.append(
                {
                    "linea": numero_linea,
                    "nombre": str(fila[0] if len(fila) > 0 else "").strip(),
                    "descripcion": str(fila[1] if len(fila) > 1 else "").strip(),
                    "precio_compra": str(fila[2] if len(fila) > 2 else "").strip(),
                    "proveedor": str(fila[3] if len(fila) > 3 else "").strip(),
                    "impuesto": str(fila[4] if len(fila) > 4 else "").strip(),
                    "margen_ganancia": str(fila[5] if len(fila) > 5 else "").strip(),
                    "imagen": str(fila[6] if len(fila) > 6 else "").strip(),
                }
            )

    return productos


def _resolver_proveedor_importacion(nombre_proveedor, proveedor_base_id):
    nombre_proveedor = (nombre_proveedor or "").strip()

    if nombre_proveedor:
        proveedor_csv = Proveedor.objects.filter(nombre__iexact=nombre_proveedor).first()
        if proveedor_csv is not None:
            return proveedor_csv

    if proveedor_base_id:
        return Proveedor.objects.filter(id=proveedor_base_id).first()

    return None


def _productos_publicos_cache_key(query):
    normalized_query = (query or "").strip().lower()
    version = cache.get_or_set(PUBLIC_PRODUCTS_CACHE_VERSION_KEY, 1, None)
    if not normalized_query:
        return f"public:productos:v{version}:all"
    digest = md5(normalized_query.encode("utf-8")).hexdigest()
    return f"public:productos:v{version}:{digest}"


def _invalidar_cache_productos_publicos():
    try:
        cache.incr(PUBLIC_PRODUCTS_CACHE_VERSION_KEY)
    except ValueError:
        cache.set(PUBLIC_PRODUCTS_CACHE_VERSION_KEY, 2, None)


def _build_productos_structured_data(productos):
    return {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "Productos Lotus Dream Spa",
        "description": (
            "Tienda publica de Lotus Dream Spa con productos de cuidado personal, "
            "bienestar y belleza disponibles para compra."
        ),
        "mainEntity": {
            "@type": "ItemList",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": posicion,
                    "item": {
                        "@type": "Product",
                        "name": producto.nombre,
                        "description": producto.descripcion or "Producto disponible en Lotus Dream Spa.",
                        "offers": {
                            "@type": "Offer",
                            "price": producto.precio_venta,
                            "priceCurrency": "COP",
                            "availability": (
                                "https://schema.org/InStock"
                                if producto.stock_disponible > 0
                                else "https://schema.org/OutOfStock"
                            ),
                        },
                    },
                }
                for posicion, producto in enumerate(productos[:12], start=1)
            ],
        },
    }


def _cargar_productos_publicos(query):
    stock_disponible_subquery = Subquery(
        Inventario.objects.filter(producto=OuterRef("pk"), stock__gt=0)
        .values("producto")
        .annotate(total_stock=Sum("stock"))
        .values("total_stock")[:1],
        output_field=IntegerField(),
    )

    productos = (
        Producto.objects.filter(activo=True)
        .annotate(stock_disponible=Coalesce(stock_disponible_subquery, Value(0), output_field=IntegerField()))
        .values("id", "nombre", "descripcion", "imagen", "precio_venta", "stock_disponible")
        .order_by("nombre")
    )

    if query:
        productos = productos.filter(
            Q(nombre__icontains=query) |
            Q(descripcion__icontains=query)
        )

    return [SimpleNamespace(**producto) for producto in productos]


def _obtener_payload_productos_publicos(query):
    cache_key = _productos_publicos_cache_key(query)
    payload = cache.get(cache_key)
    if payload is not None:
        return payload

    productos = _cargar_productos_publicos(query)
    payload = {
        "productos": productos,
        "structured_data_json": serialize_structured_data(
            _build_productos_structured_data(productos)
        ),
    }
    cache.set(cache_key, payload, PUBLIC_PRODUCTS_CACHE_TIMEOUT)
    return payload


def productos_publicos(request):
    query = (request.GET.get("q", "") or "").strip()
    payload = _obtener_payload_productos_publicos(query)
    productos = payload["productos"]

    response = render(request, "cliente/compra.html", {
        "productos": productos,
        "query": query,
        "stock_catalogo": {
            str(producto.id): producto.stock_disponible
            for producto in productos
        },
        "checkout_config": {
            "processUrl": reverse("inventario:procesar_pago"),
            "resultUrl": reverse("inventario:resultado"),
            "csrfToken": get_token(request),
        },
        "meta_title": "Tienda | Lotus Dream Spa",
        "meta_description": (
            "Compra productos de bienestar y cuidado personal en Lotus Dream Spa. "
            "Busca por nombre, revisa disponibilidad y procesa tu pedido en linea."
        ),
        "structured_data_json": payload["structured_data_json"],
    })
    return apply_public_page_cache_headers(response)


def procesar_pago(request):
    if "usuario_id" not in request.session:
        return JsonResponse(
            {"status": "error", "message": "Debes iniciar sesion para comprar.", "redirect_url": reverse("sesiones:login")},
            status=401,
        )

    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Metodo no permitido."}, status=405)

    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"status": "error", "message": "No se pudo leer el carrito enviado."}, status=400)

    carrito = payload.get("carrito") or []
    if not isinstance(carrito, list) or not carrito:
        return JsonResponse({"status": "error", "message": "Agrega al menos un producto al carrito."}, status=400)

    cliente = get_object_or_404(Usuario, id=request.session.get("usuario_id"))

    productos_ids = []
    cantidades_por_producto = {}
    for item in carrito:
        try:
            producto_id = int(item.get("id"))
            cantidad = int(item.get("cantidad") or 0)
        except (TypeError, ValueError):
            return JsonResponse({"status": "error", "message": "Hay productos invalidos en el carrito."}, status=400)

        if cantidad <= 0:
            return JsonResponse({"status": "error", "message": "La cantidad debe ser mayor a cero."}, status=400)

        productos_ids.append(producto_id)
        cantidades_por_producto[producto_id] = cantidades_por_producto.get(producto_id, 0) + cantidad

    productos = {
        producto.id: producto
        for producto in Producto.objects.filter(id__in=productos_ids, activo=True)
    }

    if len(productos) != len(cantidades_por_producto):
        return JsonResponse({"status": "error", "message": "Uno o varios productos ya no estan disponibles."}, status=400)

    for producto_id, cantidad_total in cantidades_por_producto.items():
        producto = productos[producto_id]
        stock_disponible = obtener_stock_disponible(producto)
        if stock_disponible < cantidad_total:
            return JsonResponse(
                {"status": "error", "message": f"Solo quedan {stock_disponible} unidades de {producto.nombre}."},
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
    if telefono: observaciones.append(f"Telefono: {telefono}")
    if direccion: observaciones.append(f"Direccion: {direccion}")

    with transaction.atomic():
        venta = Venta.objects.create(cliente=cliente, total=total)

        for producto_id, cantidad_total in cantidades_por_producto.items():
            producto = productos[producto_id]
            DetalleVenta.objects.create(
                venta=venta, producto=producto, cantidad=cantidad_total, precio_unitario=producto.precio_venta
            )

            items_inventario = Inventario.objects.filter(
                producto=producto, stock__gt=0
            ).order_by('fecha_ingreso')
            
            quedan_por_descontar = cantidad_total

            for item in items_inventario:
                if quedan_por_descontar <= 0:
                    break
                
                sacar = min(item.stock, quedan_por_descontar)
                item.stock -= sacar
                item.save()

                # Registro del movimiento (CORRECCIÓN: timezone.now() ahora funciona)
                MovimientoInventario.objects.create(
                    inventario=item,
                    producto=producto,
                    lote=item.lote,
                    cantidad=sacar,
                    tipo='SALIDA',
                    fecha=timezone.now()
                )
                quedan_por_descontar -= sacar

            if quedan_por_descontar > 0:
                raise ValueError(f"Inconsistencia de stock para {producto.nombre}")

        validacion = ValidacionVenta.objects.create(
            venta=venta, cliente=cliente, metodo_pago=metodo_pago,
            referencia_pago=f"WEB-{venta.id}", monto=total,
            estado="pendiente", observaciones="\n".join(observaciones),
        )

    sent = notificar_compra_pendiente(venta=venta, validacion=validacion)
    _invalidar_cache_productos_publicos()
    return JsonResponse({
        "status": "success",
        "redirect_url": reverse("inventario:resultado"),
        "warning": "" if sent else "No se pudo enviar la notificacion."
    })


def resultado_compra(request):
    return render(
        request,
        "cliente/resultado.html",
        {
            "meta_title": "Resultado de compra | Lotus Dream Spa",
            "meta_robots": "noindex,nofollow",
        },
    )


@login_required_session
def producto_comprar(request, producto_id):
    if request.method != "POST":
        return redirect("inventario:productos_publicos")

    producto = get_object_or_404(Producto, id=producto_id)
    try:
        cantidad = int(request.POST.get("cantidad") or 1)
    except ValueError:
        cantidad = 1

    cliente = get_object_or_404(Usuario, id=request.session.get("usuario_id"))
    total = producto.precio_venta * cantidad

    with transaction.atomic():
        venta = Venta.objects.create(cliente=cliente, total=total)
        DetalleVenta.objects.create(
            venta=venta, producto=producto, cantidad=cantidad, precio_unitario=producto.precio_venta
        )

        items_inventario = Inventario.objects.filter(producto=producto, stock__gt=0).order_by('fecha_ingreso')
        quedan = cantidad
        for item in items_inventario:
            if quedan <= 0: break
            sacar = min(item.stock, quedan)
            item.stock -= sacar
            item.save()
            MovimientoInventario.objects.create(
                inventario=item, producto=producto, lote=item.lote,
                cantidad=sacar, tipo='SALIDA', fecha=timezone.now()
            )
            quedan -= sacar

        if quedan > 0:
            messages.error(request, "No hay stock suficiente.")
            raise ValueError("Stock insuficiente")

        validacion, created = ValidacionVenta.objects.get_or_create(
            venta_id=venta.id,
            defaults={
                "venta": venta, "cliente": cliente, "metodo_pago": "por_confirmar",
                "referencia_pago": f"WEB-{venta.id}", "monto": total,
                "estado": "pendiente", "observaciones": "Compra directa web.",
            }
        )

    if created:
        notificar_compra_pendiente(venta=venta, validacion=validacion)
        messages.success(request, "Compra registrada.")
        _invalidar_cache_productos_publicos()
    return redirect("sesiones:perfil")


@admin_required_session
def producto_lista(request):
    query = request.GET.get("q", "")
    estado_filtro = request.GET.get("estado", "")
    proveedor_id = request.GET.get("proveedor_id", "")
    categoria_id = request.GET.get("categoria_id", "")

    productos = anotar_stock_disponible(
        queryset_productos_basico()
    )

    if query:
        productos = productos.filter(
            Q(nombre__icontains=query) |
            Q(descripcion__icontains=query)
        )

    if proveedor_id:
        productos = productos.filter(proveedor_id=proveedor_id)

    if categoria_id:
        productos = productos.filter(categoria_id=categoria_id)

    proveedores = Proveedor.objects.all().order_by("nombre")
    categorias = _categorias_producto_activas()

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
        "categoria_id": categoria_id,
        "proveedores": proveedores,
        "categorias": categorias,
    })


@admin_required_session
def producto_importar_csv(request):
    if request.method != "POST":
        return redirect("inventario:producto_lista")

    try:
        filas = _leer_productos_desde_csv(request.FILES.get("archivo_csv"))
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("inventario:producto_lista")

    proveedor_base_id = request.POST.get("proveedor_base_id")
    impuesto_default_raw = request.POST.get("impuesto_default") or "19"
    margen_default_raw = request.POST.get("margen_default") or "20"

    try:
        impuesto_default = _parse_decimal_csv(impuesto_default_raw, "Impuesto por defecto")
        margen_default = _parse_decimal_csv(margen_default_raw, "Margen por defecto")
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("inventario:producto_lista")

    categoria_default = _categoria_producto_default()
    creados = 0
    errores = []

    for fila in filas:
        nombre = fila["nombre"]
        numero_linea = fila["linea"]

        if not nombre:
            errores.append(f"Fila {numero_linea}: falta el nombre del producto.")
            continue

        if Producto.objects.filter(nombre__iexact=nombre).exists():
            errores.append(f"Fila {numero_linea}: ya existe un producto llamado {nombre}.")
            continue

        try:
            precio_compra = _parse_decimal_csv(fila["precio_compra"], "Precio de compra")
            impuesto = (
                _parse_decimal_csv(fila["impuesto"], "Impuesto")
                if fila["impuesto"]
                else impuesto_default
            )
            margen_ganancia = (
                _parse_decimal_csv(fila["margen_ganancia"], "Margen")
                if fila["margen_ganancia"]
                else margen_default
            )
        except ValueError as exc:
            errores.append(f"Fila {numero_linea}: {exc}.")
            continue

        proveedor = _resolver_proveedor_importacion(
            fila["proveedor"],
            proveedor_base_id,
        )

        if proveedor is None:
            errores.append(
                f"Fila {numero_linea}: no se encontró proveedor y tampoco se seleccionó uno por defecto."
            )
            continue

        producto = Producto(
            nombre=nombre,
            descripcion=fila["descripcion"],
            imagen=fila["imagen"] or None,
            proveedor=proveedor,
            categoria=categoria_default,
            precio_compra=precio_compra,
            impuesto=impuesto,
            margen_ganancia=margen_ganancia,
            precio_venta=_calcular_precio_venta(precio_compra, impuesto, margen_ganancia),
        )
        try:
            producto.full_clean()
            producto.save()
        except ValidationError as exc:
            errores.append(f"Fila {numero_linea}: {' '.join(exc.messages)}")
            continue
        creados += 1

    if creados:
        messages.success(request, f"Se importaron {creados} producto(s) desde el archivo CSV.")

    if errores:
        resumen = " ".join(errores[:3])
        sufijo = " ..." if len(errores) > 3 else ""
        messages.warning(
            request,
            f"Se omitieron {len(errores)} fila(s) con errores. {resumen}{sufijo}",
        )

    if creados:
        _invalidar_cache_productos_publicos()

    return redirect("inventario:producto_lista")


@admin_required_session
def producto_nuevo(request):
    if request.method == "POST":
        nombre = request.POST.get("nombre", "").strip()
        descripcion = request.POST.get("descripcion", "")
        precio_compra = _parse_decimal_form(request, "precio_compra", "0", "Precio de compra")
        impuesto = _parse_decimal_form(request, "impuesto", "19", "Impuesto")
        margen_ganancia = _parse_decimal_form(request, "margen_ganancia", "20", "Margen de ganancia")
        proveedor = _resolver_proveedor_form(request)
        categoria = _resolver_categoria_form(request)

        if not nombre:
            messages.error(request, "El nombre es obligatorio.")

        if not all([nombre, precio_compra is not None, impuesto is not None, margen_ganancia is not None, proveedor, categoria]):
            return _render_producto_form(request)

        if Producto.objects.filter(nombre__iexact=nombre).exists():
            messages.error(request, "Ya existe un producto con ese nombre")
            return _render_producto_form(request)

        producto = Producto(
            nombre=nombre,
            descripcion=descripcion,
            imagen=subir_imagen_producto(request.FILES.get("imagen")),
            proveedor=proveedor,
            categoria=categoria,
            precio_compra=precio_compra,
            impuesto=impuesto,
            margen_ganancia=margen_ganancia,
            precio_venta=_calcular_precio_venta(precio_compra, impuesto, margen_ganancia) # CORRECCIÓN: Cálculo de precio
        )

        try:
            producto.full_clean()
            producto.save()
        except ValidationError as exc:
            for error in exc.messages:
                messages.error(request, error)
            return _render_producto_form(request)

        messages.success(request, "Producto creado correctamente")
        _invalidar_cache_productos_publicos()
        return redirect("inventario:producto_lista")

    return _render_producto_form(request)


@admin_required_session
def producto_editar(request, producto_id):
    producto = get_object_or_404(queryset_productos_basico(), id=producto_id)

    if request.method == "POST":
        nombre = (request.POST.get("nombre") or "").strip()
        if not nombre:
            messages.error(request, "El nombre es obligatorio.")
            return _render_producto_form(request, producto)

        if Producto.objects.filter(nombre__iexact=nombre).exclude(id=producto.id).exists():
            messages.error(request, "Ya existe otro producto con ese nombre")
            return _render_producto_form(request, producto)

        precio_compra = _parse_decimal_form(request, "precio_compra", "0", "Precio de compra")
        impuesto = _parse_decimal_form(request, "impuesto", "19", "Impuesto")
        margen_ganancia = _parse_decimal_form(request, "margen_ganancia", "20", "Margen de ganancia")
        proveedor = _resolver_proveedor_form(request)
        categoria = _resolver_categoria_form(request)

        if not all([precio_compra is not None, impuesto is not None, margen_ganancia is not None, proveedor, categoria]):
            return _render_producto_form(request, producto)

        producto.nombre = nombre
        producto.descripcion = request.POST.get("descripcion", "")
        producto.precio_compra = precio_compra
        producto.impuesto = impuesto
        producto.margen_ganancia = margen_ganancia
        producto.precio_venta = _calcular_precio_venta(producto.precio_compra, producto.impuesto, producto.margen_ganancia)

        imagen_url = subir_imagen_producto(request.FILES.get("imagen"))
        if imagen_url:
            producto.imagen = imagen_url

        producto.proveedor = proveedor
        producto.categoria = categoria
        try:
            producto.full_clean()
            producto.save()
        except ValidationError as exc:
            for error in exc.messages:
                messages.error(request, error)
            return _render_producto_form(request, producto)

        _invalidar_cache_productos_publicos()
        return redirect("inventario:producto_lista")

    return _render_producto_form(request, producto)


@admin_required_session
def producto_detalle(request, producto_id):
    producto = get_object_or_404(
        anotar_stock_disponible(queryset_productos_basico()),
        id=producto_id,
    )
    return render(request, "inventario/dashboard/productos/detalle.html", {"producto": producto, "margen": producto.margen_ganancia})


@admin_required_session
def producto_eliminar(request, producto_id):
    producto = get_object_or_404(Producto, id=producto_id)
    if request.method == "POST":
        producto.activo = False
        producto.save()
        _invalidar_cache_productos_publicos()
    return redirect("inventario:producto_lista")

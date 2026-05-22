from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from decimal import Decimal

from apps.inventario.models import Compra, DetalleCompra, DevolucionCompra, Inventario, Producto, Proveedor
from apps.sesiones.models import Usuario


class InventarioUrlsTest(TestCase):
    def setUp(self):
        usuario = Usuario.objects.create(
            documento=1,
            nombre="Admin",
            apellido="Inv",
            correo="admin@inv.com",
            fecha_nacimiento="1990-01-01",
            clave="1234",
            rol="admin",
        )
        session = self.client.session
        session["usuario_id"] = usuario.id
        session["usuario_rol"] = "admin"
        session.save()
        self.proveedor = Proveedor.objects.create(nombre="Proveedor Base")

    def test_reverse_and_view(self):
        self.assertEqual(reverse("inventario:producto_lista"), "/inventario/productos/")
        response = self.client.get(reverse("inventario:producto_lista"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Navegación admin")

    def test_informe_muestra_sidebar_admin(self):
        response = self.client.get(reverse("inventario:informe_inventario"))

        self.assertRedirects(
            response,
            reverse("inventario:dashboard"),
            fetch_redirect_response=False,
        )

    def test_informe_redirige_a_login_sin_sesion(self):
        self.client.session.flush()

        response = self.client.get(reverse("inventario:informe_inventario"))

        self.assertRedirects(
            response,
            f"{reverse('sesiones:login')}?next={reverse('inventario:informe_inventario')}",
            fetch_redirect_response=False,
        )

    def test_reverse_importar_csv(self):
        self.assertEqual(
            reverse("inventario:producto_importar_csv"),
            "/inventario/productos/importar-csv/",
        )

    def test_importa_productos_desde_csv_con_proveedor_por_defecto(self):
        archivo = SimpleUploadedFile(
            "productos.csv",
            (
                "nombre,descripcion,precio_compra\n"
                "Serum facial,Hidratacion intensiva,25000\n"
                "Shampoo spa,Limpieza profunda,18000\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(
            reverse("inventario:producto_importar_csv"),
            {
                "archivo_csv": archivo,
                "proveedor_base_id": str(self.proveedor.id),
                "impuesto_default": "19",
                "margen_default": "20",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Producto.objects.count(), 2)
        producto = Producto.objects.get(nombre="Serum facial")
        self.assertEqual(producto.proveedor_id, self.proveedor.id)
        self.assertEqual(str(producto.precio_venta), "34750.00")
        self.assertContains(response, "Se importaron 2 producto(s)")

    def test_importacion_omite_filas_con_error(self):
        archivo = SimpleUploadedFile(
            "productos.csv",
            (
                "nombre;descripcion;precio_compra;proveedor\n"
                "Mascarilla;Recuperacion capilar;35000;Proveedor Base\n"
                "Fila sin precio;Invalida;;Proveedor Base\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(
            reverse("inventario:producto_importar_csv"),
            {
                "archivo_csv": archivo,
                "impuesto_default": "19",
                "margen_default": "20",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Producto.objects.count(), 1)
        self.assertTrue(Producto.objects.filter(nombre="Mascarilla").exists())
        self.assertContains(response, "Se omitieron 1 fila(s) con errores")

    def test_importa_con_proveedor_por_defecto_si_el_csv_trae_un_proveedor_inexistente(self):
        archivo = SimpleUploadedFile(
            "productos.csv",
            (
                "nombre;descripcion;precio_compra;proveedor\n"
                "Ampolleta;Nutricion intensa;35000;Proveedor que no existe\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(
            reverse("inventario:producto_importar_csv"),
            {
                "archivo_csv": archivo,
                "proveedor_base_id": str(self.proveedor.id),
                "impuesto_default": "19",
                "margen_default": "20",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Producto.objects.count(), 1)
        producto = Producto.objects.get(nombre="Ampolleta")
        self.assertEqual(producto.proveedor_id, self.proveedor.id)
        self.assertContains(response, "Se importaron 1 producto(s)")

    def test_catalogo_publico_no_muestra_sidebar_admin(self):
        response = self.client.get(reverse("inventario:productos_publicos"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Navegación admin")

    def test_catalogo_publico_agrupa_stock_por_producto(self):
        producto = Producto.objects.create(
            nombre="Serum publico",
            proveedor=self.proveedor,
            precio_compra=10000,
            precio_venta=18000,
            impuesto=19,
            margen_ganancia=20,
        )
        Inventario.objects.create(producto=producto, lote="L-1", stock=2, precio_venta=18000)
        Inventario.objects.create(producto=producto, lote="L-2", stock=3, precio_venta=18000)

        agotado = Producto.objects.create(
            nombre="Producto agotado",
            proveedor=self.proveedor,
            precio_compra=9000,
            precio_venta=15000,
            impuesto=19,
            margen_ganancia=20,
        )
        Inventario.objects.create(producto=agotado, lote="L-0", stock=0, precio_venta=15000)

        response = self.client.get(reverse("inventario:productos_publicos"))

        self.assertEqual(response.status_code, 200)
        productos = list(response.context["productos"])
        self.assertEqual(len(productos), 1)
        self.assertEqual(productos[0].nombre, "Serum publico")
        self.assertEqual(productos[0].stock_disponible, 5)

    def test_compra_nueva_rechaza_valores_negativos_o_en_cero(self):
        producto = Producto.objects.create(
            nombre="Aceite de prueba",
            proveedor=self.proveedor,
            precio_compra=10000,
            precio_venta=15000,
            impuesto=19,
            margen_ganancia=20,
        )

        response = self.client.post(
            reverse("inventario:compra_nueva"),
            {
                "proveedor_id": str(self.proveedor.id),
                "numero_factura": "FAC-100",
                "productos_ids[]": [str(producto.id)],
                "cantidades[]": ["0"],
                "precios[]": ["-50"],
                "impuestos[]": ["19"],
                "margenes[]": ["20"],
                "lotes[]": ["L-001"],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "mayor a cero")
        self.assertEqual(Compra.objects.count(), 0)
        self.assertEqual(DetalleCompra.objects.count(), 0)

    def test_compra_nueva_rechaza_factura_duplicada_sin_importar_mayusculas(self):
        producto = Producto.objects.create(
            nombre="Locion duplicada",
            proveedor=self.proveedor,
            precio_compra=10000,
            precio_venta=15000,
            impuesto=19,
            margen_ganancia=20,
        )
        compra = Compra.objects.create(
            proveedor=self.proveedor,
            total=10000,
            numero_factura="Fac-200",
        )
        DetalleCompra.objects.create(
            compra=compra,
            producto=producto,
            cantidad=1,
            precio_compra=Decimal("10000"),
            impuesto=Decimal("19"),
            margen_ganancia=Decimal("20"),
            lote="L-BASE",
        )

        response = self.client.post(
            reverse("inventario:compra_nueva"),
            {
                "proveedor_id": str(self.proveedor.id),
                "numero_factura": "fac-200",
                "productos_ids[]": [str(producto.id)],
                "cantidades[]": ["1"],
                "precios[]": ["10000"],
                "impuestos[]": ["19"],
                "margenes[]": ["20"],
                "lotes[]": ["L-002"],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ya existe esa factura para este proveedor")
        self.assertEqual(Compra.objects.count(), 1)

    def test_proveedor_nuevo_rechaza_duplicados_por_nombre_o_nit(self):
        Proveedor.objects.create(nombre="Proveedor duplicado", nit="900123")

        response = self.client.post(
            reverse("inventario:proveedor_nuevo"),
            {
                "nombre": "proveedor DUPLICADO",
                "telefono": "3101234567",
                "nit": "900123",
                "correo": "proveedor2@test.com",
                "direccion": "Calle 10 #20-30",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ya existe un proveedor con ese nombre, correo o NIT.")
        self.assertEqual(Proveedor.objects.filter(nombre__iexact="Proveedor duplicado").count(), 1)

    def test_proveedor_nuevo_rechaza_correo_sin_arroba(self):
        response = self.client.post(
            reverse("inventario:proveedor_nuevo"),
            {
                "nombre": "Proveedor Correo",
                "telefono": "3101234567",
                "nit": "900456",
                "correo": "proveedorcorreo.com",
                "direccion": "Calle 11 #22-33",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "El correo no es valido.")
        self.assertFalse(Proveedor.objects.filter(nombre="Proveedor Correo").exists())

    def test_compra_nueva_rechaza_impuesto_mayor_a_100(self):
        producto = Producto.objects.create(
            nombre="Producto impuesto alto",
            proveedor=self.proveedor,
            precio_compra=10000,
            precio_venta=15000,
            impuesto=19,
            margen_ganancia=20,
        )

        response = self.client.post(
            reverse("inventario:compra_nueva"),
            {
                "proveedor_id": str(self.proveedor.id),
                "numero_factura": "FAC-300",
                "productos_ids[]": [str(producto.id)],
                "cantidades[]": ["1"],
                "precios[]": ["10000"],
                "impuestos[]": ["110"],
                "margenes[]": ["20"],
                "lotes[]": ["L-003"],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "El impuesto de la fila 1 no puede superar 100.")
        self.assertEqual(Compra.objects.count(), 0)

    def test_compra_nueva_rechaza_lote_mayor_a_8_caracteres(self):
        producto = Producto.objects.create(
            nombre="Producto lote largo",
            proveedor=self.proveedor,
            precio_compra=10000,
            precio_venta=15000,
            impuesto=19,
            margen_ganancia=20,
        )

        response = self.client.post(
            reverse("inventario:compra_nueva"),
            {
                "proveedor_id": str(self.proveedor.id),
                "numero_factura": "FAC-301",
                "productos_ids[]": [str(producto.id)],
                "cantidades[]": ["1"],
                "precios[]": ["10000"],
                "impuestos[]": ["19"],
                "margenes[]": ["20"],
                "lotes[]": ["LOTE-0001"],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "El lote de la fila 1 no puede superar 8 caracteres.")
        self.assertEqual(Compra.objects.count(), 0)

    def test_devolucion_nueva_incluye_productos_disponibles_de_la_compra(self):
        producto = Producto.objects.create(
            nombre="Serum retorno",
            proveedor=self.proveedor,
            precio_compra=10000,
            precio_venta=15000,
            impuesto=19,
            margen_ganancia=20,
        )
        compra = Compra.objects.create(
            proveedor=self.proveedor,
            total=10000,
            numero_factura="DEV-100",
        )
        DetalleCompra.objects.create(
            compra=compra,
            producto=producto,
            cantidad=3,
            precio_compra=Decimal("10000"),
            impuesto=Decimal("19"),
            margen_ganancia=Decimal("20"),
            lote="L-DEV-1",
        )

        response = self.client.get(reverse("inventario:devolucion_nueva"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "compras-devolucion-data")
        self.assertContains(response, "Serum retorno")
        self.assertContains(response, "cantidad_disponible")

    def test_devolucion_nueva_rechaza_producto_que_no_pertenece_a_compra(self):
        producto_compra = Producto.objects.create(
            nombre="Crema comprada",
            proveedor=self.proveedor,
            precio_compra=10000,
            precio_venta=15000,
            impuesto=19,
            margen_ganancia=20,
        )
        producto_ajeno = Producto.objects.create(
            nombre="Producto ajeno",
            proveedor=self.proveedor,
            precio_compra=12000,
            precio_venta=18000,
            impuesto=19,
            margen_ganancia=20,
        )
        compra = Compra.objects.create(
            proveedor=self.proveedor,
            total=10000,
            numero_factura="DEV-200",
        )
        DetalleCompra.objects.create(
            compra=compra,
            producto=producto_compra,
            cantidad=2,
            precio_compra=Decimal("10000"),
            impuesto=Decimal("19"),
            margen_ganancia=Decimal("20"),
            lote="L-DEV-2",
        )

        response = self.client.post(
            reverse("inventario:devolucion_nueva"),
            {
                "compra_id": str(compra.id),
                "producto_id": str(producto_ajeno.id),
                "cantidad": "1",
                "motivo": "Producto incorrecto",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Debes seleccionar un producto válido de la compra elegida.")
        self.assertEqual(DevolucionCompra.objects.count(), 0)


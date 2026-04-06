from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.inventario.models import Producto, Proveedor
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

    def test_catalogo_publico_no_muestra_sidebar_admin(self):
        response = self.client.get(reverse("inventario:productos_publicos"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Navegación admin")

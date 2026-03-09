from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.citas.models import Servicio
from apps.inventario.models import Producto, Proveedor


class Command(BaseCommand):
    help = "Crea servicios y productos de prueba para el proyecto."

    def handle(self, *args, **options):
        proveedor, _ = Proveedor.objects.get_or_create(
            nombre="Proveedor Demo Lotus",
            defaults={
                "empresa": "Lotus Supplies SAS",
                "telefono": "3000000000",
                "correo": "proveedor.demo@lotusspa.com",
                "direccion": "Carrera 7 #128 - 45",
                "nit": "900123456-7",
                "pais": "Colombia",
            },
        )

        servicios = [
            {
                "nombre": "Masaje relajante",
                "descripcion": "Sesion corporal de 60 minutos para aliviar tension.",
                "precio": Decimal("90000.00"),
                "persona_servicio": "Laura Martinez",
            },
            {
                "nombre": "Facial hidratante",
                "descripcion": "Limpieza y nutricion profunda para el rostro.",
                "precio": Decimal("75000.00"),
                "persona_servicio": "Camila Rojas",
            },
            {
                "nombre": "Manicura semipermanente",
                "descripcion": "Cuidado de unas con esmaltado semipermanente.",
                "precio": Decimal("55000.00"),
                "persona_servicio": "Andrea Gomez",
            },
        ]

        productos = [
            {
                "nombre": "Serum facial vitamina C",
                "descripcion": "Suero antioxidante para uso diario.",
                "stock": 20,
                "precio_compra": Decimal("28000.00"),
                "precio_venta": Decimal("45000.00"),
                "iva": Decimal("19.00"),
            },
            {
                "nombre": "Mascarilla hidratante aloe",
                "descripcion": "Mascarilla calmante para piel sensible.",
                "stock": 15,
                "precio_compra": Decimal("18000.00"),
                "precio_venta": Decimal("32000.00"),
                "iva": Decimal("19.00"),
            },
            {
                "nombre": "Aceite corporal relajante",
                "descripcion": "Aceite aromatico para masaje profesional.",
                "stock": 12,
                "precio_compra": Decimal("25000.00"),
                "precio_venta": Decimal("42000.00"),
                "iva": Decimal("19.00"),
            },
        ]

        for data in servicios:
            Servicio.objects.update_or_create(nombre=data["nombre"], defaults=data)

        for data in productos:
            Producto.objects.update_or_create(
                nombre=data["nombre"],
                defaults={
                    **data,
                    "proveedor": proveedor,
                },
            )

        self.stdout.write(self.style.SUCCESS("Datos de prueba cargados correctamente."))

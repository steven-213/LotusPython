from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone


class Proveedor(models.Model):
    nombre = models.CharField(max_length=255, verbose_name="Nombre del Proveedor")
    empresa = models.CharField(max_length=255, blank=True, verbose_name="Razón Social")
    telefono = models.CharField(max_length=50, blank=True)
    correo = models.EmailField(blank=True, verbose_name="Correo Electrónico")
    direccion = models.CharField(max_length=255, blank=True)
    nit = models.CharField(max_length=50, blank=True, unique=True, verbose_name="NIT/RUC")
    pais = models.CharField(max_length=100, blank=True, default="Colombia")
    activo = models.BooleanField(default=True, verbose_name="¿Activo?")
    created_at = models.DateTimeField(default=timezone.now, verbose_name="Fecha de Creación")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Última Actualización")

    class Meta:
        verbose_name = "Proveedor"
        verbose_name_plural = "Proveedores"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Producto(models.Model):
    nombre = models.CharField(max_length=255, verbose_name="Nombre del Producto")
    descripcion = models.TextField(blank=True, verbose_name="Descripción")
    imagen = models.URLField(blank=True, null=True)
    stock = models.IntegerField(default=0, validators=[MinValueValidator(0)], verbose_name="Cantidad en Stock")
    stock_minimo = models.IntegerField(default=10, validators=[MinValueValidator(0)], verbose_name="Stock Mínimo")
    proveedor = models.ForeignKey(Proveedor, on_delete=models.SET_NULL, null=True, blank=True)
    precio_compra = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name="Precio de Compra",
    )
    precio_venta = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name="Precio de Venta",
    )
    iva = models.DecimalField(max_digits=5, decimal_places=2, default=19, verbose_name="IVA (%)")
    activo = models.BooleanField(default=True, verbose_name="¿Activo?")
    created_at = models.DateTimeField(default=timezone.now, verbose_name="Fecha de Creación")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Última Actualización")

    class Meta:
        verbose_name = "Producto"
        verbose_name_plural = "Productos"
        ordering = ["nombre"]
        indexes = [models.Index(fields=["nombre"]), models.Index(fields=["stock"])]

    def __str__(self):
        return self.nombre

    @property
    def margen_ganancia(self):
        """Calcula el margen de ganancia en porcentaje"""
        if self.precio_compra and self.precio_compra > 0:
            return ((self.precio_venta - self.precio_compra) / self.precio_compra) * 100
        return 0

    @property
    def necesita_reorden(self):
        """Verifica si el producto necesita reorden"""
        return self.stock <= self.stock_minimo

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.precio_venta < self.precio_compra:
            raise ValidationError("El precio de venta no puede ser menor que el precio de compra.")


class Compra(models.Model):
    ESTADO_CHOICES = [
        ("pendiente", "Pendiente"),
        ("completada", "Completada"),
        ("cancelada", "Cancelada"),
    ]

    proveedor = models.ForeignKey(Proveedor, on_delete=models.PROTECT)
    fecha = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Compra")
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Total")
    numero_factura = models.CharField(max_length=100, blank=True, verbose_name="Número de Factura")
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="completada")
    observaciones = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now, verbose_name="Creado")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Actualizado")

    class Meta:
        verbose_name = "Compra"
        verbose_name_plural = "Compras"
        ordering = ["-fecha"]

    def __str__(self):
        return f"Compra #{self.id} - {self.proveedor.nombre} ({self.fecha.strftime('%d/%m/%Y')})"


class DetalleCompra(models.Model):
    compra = models.ForeignKey(Compra, on_delete=models.CASCADE, related_name="detalles")
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    cantidad = models.IntegerField(validators=[MinValueValidator(1)])
    precio_compra = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Precio Unitario")
    forma_pago = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Detalle de Compra"
        verbose_name_plural = "Detalles de Compra"
        unique_together = ("compra", "producto")

    def __str__(self):
        return f"{self.producto.nombre} x{self.cantidad}"

    @property
    def subtotal(self):
        return self.cantidad * self.precio_compra


class DevolucionCompra(models.Model):
    ESTADO_CHOICES = [
        ("pendiente", "Pendiente"),
        ("aprobada", "Aprobada"),
        ("rechazada", "Rechazada"),
    ]

    compra = models.ForeignKey(Compra, on_delete=models.CASCADE, related_name="devoluciones")
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    cantidad = models.IntegerField(validators=[MinValueValidator(1)], verbose_name="Cantidad Devuelta")
    motivo = models.TextField(blank=True, verbose_name="Motivo de la Devolución")
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="pendiente")
    fecha = models.DateTimeField(default=timezone.now, verbose_name="Fecha de Devolución")
    autorizado_por = models.CharField(max_length=255, blank=True, verbose_name="Autorizado Por")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Devolución de Compra"
        verbose_name_plural = "Devoluciones de Compra"
        ordering = ["-fecha"]

    def __str__(self):
        return f"Dev #{self.id} - {self.producto.nombre} x{self.cantidad}"

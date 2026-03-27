from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Proveedor(models.Model):
    nombre = models.CharField(max_length=255, verbose_name="Nombre del Proveedor")
    empresa = models.CharField(max_length=255, blank=True, verbose_name="Razon Social")
    telefono = models.CharField(max_length=50, blank=True)
    correo = models.EmailField(blank=True, verbose_name="Correo Electronico")
    direccion = models.CharField(max_length=255, blank=True)
    nit = models.CharField(max_length=50, blank=True, unique=True, verbose_name="NIT/RUC")
    pais = models.CharField(max_length=100, blank=True, default="Colombia")
    activo = models.BooleanField(default=True, verbose_name="Activo")
    created_at = models.DateTimeField(default=timezone.now, verbose_name="Fecha de Creacion")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Ultima Actualizacion")

    class Meta:
        verbose_name = "Proveedor"
        verbose_name_plural = "Proveedores"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Producto(models.Model):
    nombre = models.CharField(max_length=255, verbose_name="Nombre del Producto")
    descripcion = models.TextField(blank=True, verbose_name="Descripcion")
    imagen = models.URLField(blank=True, null=True)
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
    iva = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=19,
        verbose_name="IVA (%)",
        db_column="impuesto",
    )
    margen_ganancia = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=20,
        db_column="margen_ganancia",
    )
    activo = models.BooleanField(default=True, verbose_name="Activo")
    created_at = models.DateTimeField(default=timezone.now, verbose_name="Fecha de Creacion")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Ultima Actualizacion")

    class Meta:
        verbose_name = "Producto"
        verbose_name_plural = "Productos"
        ordering = ["nombre"]
        indexes = [models.Index(fields=["nombre"])]

    def __str__(self):
        return self.nombre

    @property
    def stock_real(self):
        lotes = list(self.lotes.values_list("stock", flat=True))
        if lotes:
            return sum(max(stock, 0) for stock in lotes)
        return 0

    @property
    def stock(self):
        return self.stock_real

    @property
    def stock_minimo(self):
        return 10

    @property
    def necesita_reorden(self):
        return self.stock <= self.stock_minimo

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.precio_venta < self.precio_compra:
            raise ValidationError("El precio de venta no puede ser menor que el precio de compra.")


class Compra(models.Model):
    proveedor = models.ForeignKey(Proveedor, on_delete=models.PROTECT)
    fecha = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Compra")
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Total")
    numero_factura = models.CharField(max_length=100, blank=True, verbose_name="Numero de Factura")
    observaciones = models.TextField(blank=True)

    class Meta:
        verbose_name = "Compra"
        verbose_name_plural = "Compras"
        ordering = ["-fecha"]

    def __str__(self):
        return f"Compra #{self.id} - {self.proveedor.nombre} ({self.fecha.strftime('%d/%m/%Y')})"

    @property
    def estado(self):
        return "completada"


class DetalleCompra(models.Model):
    compra = models.ForeignKey(Compra, on_delete=models.CASCADE, related_name="detalles")
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    cantidad = models.IntegerField(validators=[MinValueValidator(1)])
    precio_compra = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Precio Unitario")
    impuesto = models.DecimalField(max_digits=5, decimal_places=2, default=19, db_column="impuesto")
    margen_ganancia = models.DecimalField(max_digits=5, decimal_places=2, default=20, db_column="margen_ganancia")
    lote = models.CharField(max_length=100, blank=True, verbose_name="Lote")

    class Meta:
        verbose_name = "Detalle de Compra"
        verbose_name_plural = "Detalles de Compra"
        unique_together = ("compra", "producto", "lote")

    def __str__(self):
        return f"{self.producto.nombre} x{self.cantidad}"

    @property
    def subtotal(self):
        return self.cantidad * self.precio_compra


class Inventario(models.Model):
    producto = models.ForeignKey(
        Producto,
        on_delete=models.PROTECT,
        related_name="lotes",
    )
    lote = models.CharField(max_length=100, verbose_name="Lote")
    stock = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name="Stock disponible",
    )
    precio_venta = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    fecha_ingreso = models.DateTimeField(default=timezone.now, verbose_name="Fecha de ingreso")

    class Meta:
        verbose_name = "Lote de Inventario"
        verbose_name_plural = "Lotes de Inventario"
        ordering = ["fecha_ingreso", "id"]
        unique_together = ("producto", "lote")

    def __str__(self):
        return f"{self.producto.nombre} - {self.lote}"


class DevolucionCompra(models.Model):
    ESTADO_CHOICES = [
        ("pendiente", "Pendiente"),
        ("aprobada", "Aprobada"),
        ("rechazada", "Rechazada"),
    ]

    compra = models.ForeignKey(Compra, on_delete=models.CASCADE, related_name="devoluciones")
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    cantidad = models.IntegerField(validators=[MinValueValidator(1)], verbose_name="Cantidad Devuelta")
    motivo = models.TextField(blank=True, verbose_name="Motivo de la Devolucion")
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="pendiente")
    fecha = models.DateTimeField(default=timezone.now, verbose_name="Fecha de Devolucion")
    autorizado_por = models.CharField(max_length=255, blank=True, verbose_name="Autorizado Por")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Devolucion de Compra"
        verbose_name_plural = "Devoluciones de Compra"
        ordering = ["-fecha"]

    def __str__(self):
        return f"Dev #{self.id} - {self.producto.nombre} x{self.cantidad}"

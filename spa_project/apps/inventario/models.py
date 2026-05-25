from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone
from django.core.exceptions import ValidationError


# =========================
# PROVEEDOR
# =========================
class Proveedor(models.Model):
    nombre = models.CharField(max_length=255, verbose_name="Nombre del Proveedor")
    empresa = models.CharField(max_length=255, blank=True, verbose_name="Razón Social")
    telefono = models.CharField(max_length=50, blank=True)
    correo = models.EmailField(blank=True)
    direccion = models.CharField(max_length=255, blank=True)
    nit = models.CharField(max_length=50, blank=True, unique=True)
    pais = models.CharField(max_length=100, blank=True, default="Colombia")
    activo = models.BooleanField(default=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


# =========================
# ESPECIFICACIONES (CATÁLOGO)
# =========================
class Especificaciones(models.Model):
    nombre = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.nombre


# =========================
# PRODUCTO (DEFINE REGLAS)
# =========================
class Producto(models.Model):
    nombre = models.CharField(max_length=255, unique=True)
    descripcion = models.TextField(blank=True)
    imagen = models.URLField(blank=True, null=True)
    precio_compra = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    impuesto = models.DecimalField(max_digits=5, decimal_places=2, default=19)
    margen_ganancia = models.DecimalField(max_digits=5, decimal_places=2, default=20)
    precio_venta = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    activo = models.BooleanField(default=True)
    proveedor = models.ForeignKey(Proveedor,on_delete=models.SET_NULL,null=True)
    especificaciones = models.ManyToManyField(Especificaciones,blank=True,related_name="productos")

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.nombre

    def clean(self):
        if self.precio_venta < self.precio_compra:
            raise ValidationError("El precio de venta no puede ser menor que el de compra.")


# =========================
# COMPRA
# =========================
class Compra(models.Model):
    proveedor = models.ForeignKey(Proveedor, on_delete=models.PROTECT)
    numero_factura = models.CharField(max_length=100, blank=True)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    observaciones = models.TextField(blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Compra #{self.id}"


# =========================
# DETALLE COMPRA (DONDE SE INGRESA TODO)
# =========================
class DetalleCompra(models.Model):
    compra = models.ForeignKey(Compra,on_delete=models.CASCADE,related_name="detalles")
    producto = models.ForeignKey(Producto,on_delete=models.PROTECT)
    cantidad = models.IntegerField(validators=[MinValueValidator(1)])
    precio_compra = models.DecimalField(max_digits=10,decimal_places=2)
    impuesto = models.DecimalField(max_digits=5,decimal_places=2,default=19)
    margen_ganancia = models.DecimalField(max_digits=5,decimal_places=2,default=20)
    lote = models.CharField(max_length=100)
    fecha_vencimiento = models.DateField(null=True,blank=True)
    pao = models.CharField(max_length=50,null=True,blank=True)

    def clean(self):

        especs = self.producto.especificaciones.all()

        requiere_vencimiento = especs.filter(
            nombre="fecha_vencimiento"
        ).exists()

        requiere_pao = especs.filter(
            nombre="pao"
        ).exists()

        if requiere_vencimiento and not self.fecha_vencimiento:
            raise ValidationError({
                "fecha_vencimiento":
                "Este producto requiere fecha de vencimiento."
            })

        if requiere_pao and not self.pao:
            raise ValidationError({
                "pao":
                "Este producto requiere PAO."
            })

    def save(self, *args, **kwargs):

        # Ejecuta validaciones
        self.full_clean()

        super().save(*args, **kwargs)

        impuesto_valor = (
            self.precio_compra * (self.impuesto / 100)
        )

        ganancia_valor = (
            self.precio_compra * (self.margen_ganancia / 100)
        )

        precio_venta = (
            self.precio_compra +
            impuesto_valor +
            ganancia_valor
        )

        inventario, created = Inventario.objects.get_or_create(
            producto=self.producto,
            lote=self.lote,
            defaults={
                "stock": 0,
                "precio_venta": precio_venta,
                "fecha_vencimiento": self.fecha_vencimiento,
                "pao": self.pao,
            }
        )

        inventario.stock += self.cantidad
        inventario.precio_venta = precio_venta

        if self.fecha_vencimiento:
            inventario.fecha_vencimiento = self.fecha_vencimiento

        if self.pao:
            inventario.pao = self.pao

        inventario.save()

        self.producto.precio_compra = self.precio_compra
        self.producto.precio_venta = precio_venta
        self.producto.save()

        MovimientoInventario.objects.create(
            inventario=inventario,
            producto=self.producto,
            lote=self.lote,
            cantidad=self.cantidad,
            tipo="INGRESO"
        )

    def __str__(self):
        return f"{self.producto.nombre} x {self.cantidad}"

# =========================
# INVENTARIO (RESULTADO FINAL)
# =========================
class Inventario(models.Model):
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    lote = models.CharField(max_length=100)
    stock = models.IntegerField(default=0)
    precio_venta = models.DecimalField(max_digits=10, decimal_places=2)
    fecha_vencimiento = models.DateField(null=True, blank=True)
    pao = models.CharField(max_length=50, null=True, blank=True)
    fecha_ingreso = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.producto.nombre} - {self.lote}"


# =========================
# MOVIMIENTOS
# =========================
class MovimientoInventario(models.Model):

    TIPO_MOVIMIENTO = [
        ("INGRESO", "Ingreso"),
        ("SALIDA", "Salida"),
        ("DEVOLUCION", "Devolución"),
    ]

    inventario = models.ForeignKey(
        Inventario,
        on_delete=models.CASCADE,
        related_name="movimientos"
    )

    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    lote = models.CharField(max_length=100)
    cantidad = models.IntegerField(validators=[MinValueValidator(1)])
    tipo = models.CharField(max_length=15, choices=TIPO_MOVIMIENTO)
    fecha = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.tipo} - {self.producto.nombre} ({self.cantidad})"


# =========================
# DEVOLUCIONES
# =========================
class DevolucionCompra(models.Model):
    ESTADO_CHOICES = [
        ("pendiente", "Pendiente"),
        ("aprobada", "Aprobada"),
        ("rechazada", "Rechazada"),
    ]

    compra = models.ForeignKey(Compra, on_delete=models.CASCADE, related_name="devoluciones")
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    cantidad = models.IntegerField(validators=[MinValueValidator(1)])
    motivo = models.TextField(blank=True)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="pendiente")
    fecha = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-fecha"]

    def __str__(self):
        return f"Dev #{self.id} - {self.producto.nombre} x{self.cantidad}"
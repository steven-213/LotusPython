from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models


class Venta(models.Model):
    cliente = models.ForeignKey("sesiones.Usuario", on_delete=models.PROTECT, null=True, blank=True)
    reserva = models.OneToOneField(
        "citas.Reserva",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="venta_asociada",
    )
    fecha = models.DateTimeField(auto_now_add=True)
    subtotal_servicios = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f"Venta {self.id}"

    @property
    def cliente_facturacion(self):
        return self.cliente

    @property
    def cliente_nombre_completo(self):
        cliente = self.cliente_facturacion
        if not cliente:
            return "Cliente no disponible"
        return f"{cliente.nombre} {cliente.apellido}".strip()

    @property
    def cliente_correo(self):
        cliente = self.cliente_facturacion
        return cliente.correo if cliente else ""

    @property
    def cliente_documento(self):
        cliente = self.cliente_facturacion
        return cliente.documento if cliente else ""

    @property
    def total_factura(self):
        return (self.subtotal_servicios or Decimal("0")) + (self.total or Decimal("0"))


class DetalleVenta(models.Model):
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name="detalles")
    producto = models.ForeignKey("inventario.Producto", on_delete=models.PROTECT)
    cantidad = models.IntegerField()
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)


class ValidacionVenta(models.Model):
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name="validaciones")
    cliente = models.ForeignKey("sesiones.Usuario", on_delete=models.PROTECT, null=True, blank=True)
    metodo_pago = models.CharField(max_length=50, blank=True)
    referencia_pago = models.CharField(max_length=100, blank=True)
    monto = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    estado = models.CharField(max_length=50, default="pendiente")
    validado_por = models.BigIntegerField(null=True, blank=True)
    fecha_validacion = models.DateTimeField(auto_now_add=True)
    observaciones = models.TextField(blank=True)

    @property
    def cliente_facturacion(self):
        return self.cliente


class SolicitudDevolucionVenta(models.Model):
    ESTADO_PENDIENTE = "pendiente"
    ESTADO_APROBADA = "aprobada"
    ESTADO_RECHAZADA = "rechazada"
    ESTADO_CHOICES = [
        (ESTADO_PENDIENTE, "Pendiente"),
        (ESTADO_APROBADA, "Aprobada"),
        (ESTADO_RECHAZADA, "Rechazada"),
    ]

    detalle_venta = models.ForeignKey(
        DetalleVenta,
        on_delete=models.CASCADE,
        related_name="solicitudes_devolucion",
    )
    cliente = models.ForeignKey(
        "sesiones.Usuario",
        on_delete=models.PROTECT,
        related_name="solicitudes_devolucion_compra",
    )
    cantidad = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    motivo = models.TextField()
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default=ESTADO_PENDIENTE,
    )
    comentario_admin = models.TextField(blank=True)
    fecha_solicitud = models.DateTimeField(auto_now_add=True)
    fecha_respuesta = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-fecha_solicitud", "-id"]
        verbose_name = "Solicitud de devolucion de venta"
        verbose_name_plural = "Solicitudes de devolucion de venta"

    def __str__(self):
        return f"Devolucion #{self.id} - Venta {self.detalle_venta.venta_id}"

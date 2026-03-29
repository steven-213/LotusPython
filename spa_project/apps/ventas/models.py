from django.core.validators import MinValueValidator
from django.db import models


class Venta(models.Model):
    cliente = models.ForeignKey("sesiones.Usuario", on_delete=models.PROTECT)
    fecha = models.DateTimeField(auto_now_add=True)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f"Venta {self.id}"


class DetalleVenta(models.Model):
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name="detalles")
    producto = models.ForeignKey("inventario.Producto", on_delete=models.PROTECT)
    cantidad = models.IntegerField()
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)


class ValidacionVenta(models.Model):
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name="validaciones")
    cliente = models.ForeignKey("sesiones.Usuario", on_delete=models.PROTECT)
    metodo_pago = models.CharField(max_length=50, blank=True)
    referencia_pago = models.CharField(max_length=100, blank=True)
    monto = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    estado = models.CharField(max_length=50, default="pendiente")
    validado_por = models.BigIntegerField(null=True, blank=True)
    fecha_validacion = models.DateTimeField(auto_now_add=True)
    observaciones = models.TextField(blank=True)


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

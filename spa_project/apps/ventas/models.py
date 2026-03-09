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

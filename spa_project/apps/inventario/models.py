from django.db import models
from decimal import Decimal
from django.db.models import Sum, F

class Proveedor(models.Model):
    nombre = models.CharField(max_length=255)
    empresa = models.CharField(max_length=255, blank=True)
    telefono = models.CharField(max_length=50, blank=True)
    correo = models.EmailField(blank=True)
    direccion = models.CharField(max_length=255, blank=True)
    nit = models.CharField(max_length=50, blank=True)
    pais = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.nombre
    
class Impuesto(models.Model):
    nombre = models.CharField(max_length=100)
    porcentaje = models.DecimalField(max_digits=5,decimal_places=2)

    def __str__(self):
        return f"{self.nombre} ({self.porcentaje}%)"


class Producto(models.Model):
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True)  
    stock = models.IntegerField(default=0)
    precio_compra = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    impuesto = models.ForeignKey(Impuesto, on_delete=models.SET_NULL, null=True, blank=True)
    precio_venta = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    proveedor = models.ForeignKey(Proveedor, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return self.nombre
    
    def save(self, *args, **kwargs):

        precio = float(self.precio_compra)

        if self.impuesto:
            iva = precio * float(self.impuesto.porcentaje) / 100
        else:
            iva = 0

        precio_iva = precio + iva
        self.precio_venta = precio_iva + (precio_iva * 0.20)

        super().save(*args, **kwargs)


class Compra(models.Model):
    fechaCompra = models.DateField(auto_now_add=True)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    numero_factura = models.CharField(max_length=100, blank=True)
    proveedor = models.ForeignKey(Proveedor, on_delete=models.PROTECT, null=True, blank=True)

    def actualizar_total(self):
        total = self.detallecompra_set.aggregate(
            total=Sum(F('cantidad') * F('precio_compra'))
        )['total']
    
        self.total = total or 0
        self.save()

    def __str__(self):
        return f"Compra {self.id} - {self.fechaCompra}"


class DetalleCompra(models.Model):

    unCompra = models.ForeignKey(Compra, on_delete=models.CASCADE)
    unProducto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    lote = models.CharField(max_length=15)
    fechaVencimiento = models.DateField()
    cantidad = models.BigIntegerField()
    precio_compra = models.DecimalField(max_digits=10, decimal_places=2)

    def save(self, *args, **kwargs):

        cantidad = int(self.cantidad)
        valor = Decimal(self.precio_compra)

        # actualizar stock
        producto = self.unProducto
        producto.stock += cantidad
        producto.save()

        super().save(*args, **kwargs)

        # actualizar total compra
        self.unCompra.actualizar_total()

    def __str__(self):
        return f"{self.unProducto.nombre} x {self.cantidad}"




class DevolucionCompra(models.Model):
    compra = models.ForeignKey(Compra, on_delete=models.CASCADE)
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    cantidad = models.IntegerField()
    motivo = models.TextField(blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

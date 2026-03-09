from django.db import models
from decimal import Decimal
from django.db.models import Sum, F


class Users(models.Model):
    documento = models.BigIntegerField(unique=True)
    nombre = models.CharField(max_length=50)
    apellido = models.CharField(max_length=50)  
    correo = models.EmailField()
    fechaNacimiento = models.DateField()
    clave = models.CharField(max_length=128)

    def __str__(self):
        return self.nombre


class Producto(models.Model):
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField()
    precio = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return self.nombre
    

class Servicio(models.Model):
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField()
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    imagen = models.ImageField(upload_to='servicios/', blank=True, null=True)

    def __str__(self):
        return self.nombre
    

class Cita(models.Model):
    title = models.CharField(max_length=200)
    startDate = models.DateTimeField()
    endDate = models.DateTimeField()
    allDay = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.title} ({self.startDate})"
    

class Venta(models.Model):
    cliente = models.CharField(max_length=100)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    fecha_inicio = models.DateTimeField()
    fecha_fin = models.DateTimeField()
    descripcion = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Venta {self.id} - {self.cliente}"


# -----------------------------
# PROVEEDORES
# -----------------------------

class Proveedor(models.Model):
    nombre = models.CharField(max_length=50)
    contacto = models.EmailField()
    
    def __str__(self):
        return self.nombre


# -----------------------------
# PRODUCTO EN INVENTARIO
# -----------------------------

class ProductoInventario(models.Model):
    nombre = models.CharField(max_length=50)
    descripcion = models.TextField()
    proveedor = models.ForeignKey(Proveedor, on_delete=models.CASCADE)
    lote = models.CharField(max_length=15)
    fechaVencimiento = models.DateField()

    stock = models.BigIntegerField(default=0)

    valor = models.DecimalField(max_digits=12, decimal_places=2)
    precio = models.DecimalField(max_digits=12, decimal_places=2)   
    precioFinal = models.DecimalField(max_digits=12, decimal_places=2)
    
    def __str__(self):
        return f"{self.nombre} - Stock: {self.stock}"


# -----------------------------
# COMPRA
# -----------------------------

class Compra(models.Model):
    fechaCompra = models.DateField(auto_now_add=True)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def actualizar_total(self):
        total = self.detallecompra_set.aggregate(
            total=Sum(F('cantidad') * F('valor'))
        )['total']

        self.total = total or 0
        self.save()

    def __str__(self):
        return f"Compra {self.id} - {self.fechaCompra}"


# -----------------------------
# DETALLE COMPRA
# -----------------------------

class DetalleCompra(models.Model):

    unCompra = models.ForeignKey(Compra, on_delete=models.CASCADE)
    unProducto = models.ForeignKey(ProductoInventario, on_delete=models.CASCADE)

    lote = models.CharField(max_length=15)
    fechaVencimiento = models.DateField()

    cantidad = models.BigIntegerField()

    proveedor = models.ForeignKey(Proveedor, on_delete=models.CASCADE)

    valor = models.DecimalField(max_digits=12, decimal_places=2)

    total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    def save(self, *args, **kwargs):

        cantidad = int(self.cantidad)
        valor = Decimal(self.valor)

        self.total = valor * cantidad

        # Actualizar stock
        producto = self.unProducto
        producto.stock += cantidad
        producto.save()

        super().save(*args, **kwargs)

        # actualizar total compra
        self.unCompra.actualizar_total()

    def __str__(self):
        return f"{self.unProducto.nombre} x {self.cantidad}"


# -----------------------------
# VENTA INVENTARIO
# -----------------------------

class VentaInventario(models.Model):

    unProducto = models.ForeignKey(ProductoInventario, on_delete=models.CASCADE)

    fechaVenta = models.DateField()

    cantidad = models.BigIntegerField()

    valor = models.DecimalField(max_digits=12, decimal_places=2)

    total = models.DecimalField(max_digits=12, decimal_places=2)

    def save(self, *args, **kwargs):

        cantidad = int(self.cantidad)

        self.total = self.valor * cantidad

        producto = self.unProducto

        # evitar stock negativo
        if producto.stock < cantidad:
            raise ValueError("No hay suficiente stock para la venta")

        producto.stock -= cantidad
        producto.save()

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Venta {self.unProducto.nombre}"


# -----------------------------
# INVENTARIO GENERAL
# -----------------------------

class Inventario(models.Model):

    unProducto = models.ForeignKey(ProductoInventario, on_delete=models.CASCADE)

    cantidadDisponible = models.BigIntegerField()

    estado = models.CharField(max_length=15)

    def save(self, *args, **kwargs):

        producto = self.unProducto

        producto.stock += int(self.cantidadDisponible)

        producto.save()

        super().save(*args, **kwargs)
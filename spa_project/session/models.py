from django.db import models

class Users(models.Model):
    documento = models.BigIntegerField(unique=True)
    nombre = models.CharField(max_length=50)
    apellido = models.CharField(max_length=50)
    correo = models.EmailField()
    fechaNacimiento = models.DateField()
    clave = models.CharField(max_length=128)

    def __str__(self):
        return self.nombre


class Proveedor(models.Model):
    nombre = models.CharField(max_length= 50)
    contacto = models.EmailField()
    
    def __str__(self):
        return self.nombre

class Producto(models.Model):
    nombre = models.CharField(max_length= 50)
    descripcion = models.TextField()
    proveedor = models.ForeignKey(Proveedor, on_delete=models.CASCADE)
    stock = models.BigIntegerField()
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    precio = models.DecimalField(max_digits=12, decimal_places=2)
    precioFinal = models.DecimalField(max_digits=12, decimal_places=2)
    
    def __str__(self):
        return f"{self.nombre} - Stock: {self.stock}"


class Compra(models.Model):
    fechaCompra = models.DateField()
    total = models.DecimalField(max_digits=12, decimal_places=2)



class DetallleCompra(models.Model):
    unCompra = models.ForeignKey(Compra, on_delete=models.CASCADE)
    unProducto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    lote = models.CharField(max_length=15)
    fechaVencimiento = models.DateField()
    cantidad = models.BigIntegerField()
    proveedor = models.ForeignKey(Proveedor, on_delete=models.CASCADE)
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    
    def save(self, *args, **kwargs):
        self.total = self.valor * self.cantidad
        
        self.unProducto.stock += self.cantidad
        self.unProducto.save()
        super().save(*args, **kwargs)
        
    def __str__(self):
        return f"Compra {self.unProducto.nombre} - {self.cantidad}"
    

    

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
from django.db import models


class Servicio(models.Model):
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True)
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    persona_servicio = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return self.nombre


class Cita(models.Model):
    ESTADOS = [
        ("programada", "Programada"),
        ("confirmada", "Confirmada"),
        ("cancelada", "Cancelada"),
        ("finalizada", "Finalizada"),
    ]

    cliente = models.ForeignKey("sesiones.Usuario", on_delete=models.PROTECT)
    servicio = models.ForeignKey(Servicio, on_delete=models.PROTECT)
    fecha_inicio = models.DateTimeField()
    fecha_fin = models.DateTimeField()
    estado = models.CharField(max_length=50, choices=ESTADOS, default="programada")
    notas = models.TextField(blank=True)

    def __str__(self):
        return f"{self.cliente.nombre} - {self.servicio.nombre}"

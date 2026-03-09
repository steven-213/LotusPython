from django.db import models


class Usuario(models.Model):
    ROL_ADMIN = "admin"
    ROL_CLIENTE = "cliente"
    ROLES = [
        (ROL_ADMIN, "Administrador"),
        (ROL_CLIENTE, "Cliente"),
    ]

    documento = models.BigIntegerField(unique=True)
    nombre = models.CharField(max_length=50)
    apellido = models.CharField(max_length=50)
    correo = models.EmailField()
    fecha_nacimiento = models.DateField()
    clave = models.CharField(max_length=128)
    rol = models.CharField(max_length=20, choices=ROLES, default=ROL_CLIENTE)
    fecha_registro = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nombre} {self.apellido}"

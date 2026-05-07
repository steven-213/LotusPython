import uuid

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


class RegistroPendiente(models.Model):
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    documento = models.BigIntegerField(unique=True)
    nombre = models.CharField(max_length=50)
    apellido = models.CharField(max_length=50)
    correo = models.EmailField(unique=True)
    fecha_nacimiento = models.DateField()
    clave = models.CharField(max_length=128)
    codigo = models.CharField(max_length=128)
    codigo_expira_en = models.DateTimeField()
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-actualizado_en",)

    def __str__(self):
        return f"Registro pendiente {self.correo}"


class RecuperacionClave(models.Model):
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    usuario = models.OneToOneField(
        Usuario,
        on_delete=models.CASCADE,
        related_name="recuperacion_clave",
    )
    correo = models.EmailField()
    codigo = models.CharField(max_length=128)
    codigo_expira_en = models.DateTimeField()
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-actualizado_en",)

    def __str__(self):
        return f"Recuperacion de clave {self.correo}"

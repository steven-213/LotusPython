from django.db import models

class Users(models.Model):
    documento = models.BigIntegerField(unique=True)
    nombre = models.CharField(max_length=50)
    apellido = models. CharField(max_length=50)
    correo = models. EmailField()
    fechaNacimiento = models. DateField()
    clave = models.CharField(max_length=128)
    def _str_(self):
        return self.nombre


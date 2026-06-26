import secrets
from django.db import models
from django.utils import timezone
from datetime import timedelta


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
    activo = models.BooleanField(default=True)
    direccion = models.TextField(null=True, blank=True)
    telefono = models.DecimalField(max_digits=20, decimal_places=0, null=True, blank=True)
    imagen_perfil = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return f"{self.nombre} {self.apellido}"


class PasswordResetToken(models.Model):
    """Modelo para almacenar tokens de reseteo de contraseña"""
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='password_reset_tokens')
    token = models.CharField(max_length=128, unique=True, db_index=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_expiracion = models.DateTimeField()
    utilizado = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-fecha_creacion']
    
    @staticmethod
    def generar_token_para_usuario(usuario, horas_expiracion=24):
        """Genera un nuevo token para reseteo de contraseña"""
        token = secrets.token_urlsafe(32)
        fecha_expiracion = timezone.now() + timedelta(hours=horas_expiracion)
        
        # Invalidar tokens previos no utilizados
        PasswordResetToken.objects.filter(
            usuario=usuario,
            utilizado=False
        ).update(utilizado=True)
        
        return PasswordResetToken.objects.create(
            usuario=usuario,
            token=token,
            fecha_expiracion=fecha_expiracion
        )
    
    def es_valido(self):
        """Verifica si el token es válido (no expirado y no utilizado)"""
        return not self.utilizado and timezone.now() < self.fecha_expiracion
    
    def marcar_como_utilizado(self):
        """Marca el token como utilizado"""
        self.utilizado = True
        self.save()
    
    def __str__(self):
        return f"Token para {self.usuario.correo} - {'Válido' if self.es_valido() else 'Inválido'}"

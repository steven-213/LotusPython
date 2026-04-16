from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models
from django.template.defaultfilters import slugify
from django.utils import timezone


class PlanMembresia(models.Model):
    nombre = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    subtitulo = models.CharField(max_length=140, blank=True)
    descripcion = models.TextField(blank=True)
    beneficios = models.TextField(help_text="Escribe un beneficio por linea.")
    precio = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    duracion_dias = models.PositiveIntegerField(default=30)
    insignia = models.CharField(max_length=80, blank=True)
    destacado = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)
    orden = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["orden", "precio", "id"]

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nombre)
        super().save(*args, **kwargs)

    @property
    def beneficios_lista(self):
        return [linea.strip() for linea in (self.beneficios or "").splitlines() if linea.strip()]


class MembresiaUsuario(models.Model):
    ESTADO_ACTIVA = "activa"
    ESTADO_CANCELADA = "cancelada"
    ESTADO_VENCIDA = "vencida"
    ESTADO_REEMPLAZADA = "reemplazada"
    ESTADO_CHOICES = [
        (ESTADO_ACTIVA, "Activa"),
        (ESTADO_CANCELADA, "Cancelada"),
        (ESTADO_VENCIDA, "Vencida"),
        (ESTADO_REEMPLAZADA, "Reemplazada"),
    ]

    ORIGEN_WEB = "web"
    ORIGEN_ADMIN = "admin"
    ORIGENES = [
        (ORIGEN_WEB, "Web"),
        (ORIGEN_ADMIN, "Administrador"),
    ]

    usuario = models.ForeignKey(
        "sesiones.Usuario",
        on_delete=models.PROTECT,
        related_name="membresias",
    )
    plan = models.ForeignKey(
        PlanMembresia,
        on_delete=models.PROTECT,
        related_name="membresias_usuario",
    )
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default=ESTADO_ACTIVA)
    fecha_inicio = models.DateTimeField(default=timezone.now)
    fecha_fin = models.DateTimeField()
    precio_pagado = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    origen = models.CharField(max_length=20, choices=ORIGENES, default=ORIGEN_WEB)
    notas = models.TextField(blank=True)
    creada_por = models.ForeignKey(
        "sesiones.Usuario",
        on_delete=models.SET_NULL,
        related_name="membresias_creadas",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fecha_inicio", "-id"]
        indexes = [
            models.Index(fields=["estado", "fecha_fin"], name="memb_estado_fin_idx"),
            models.Index(fields=["usuario", "estado"], name="memb_usuario_estado_idx"),
        ]

    def __str__(self):
        return f"{self.usuario} - {self.plan.nombre}"

    def clean(self):
        if self.fecha_fin and self.fecha_inicio and self.fecha_fin <= self.fecha_inicio:
            raise ValidationError("La fecha fin debe ser posterior a la fecha inicio.")

    def save(self, *args, **kwargs):
        if not self.fecha_fin:
            self.fecha_fin = self.fecha_inicio + timedelta(days=self.plan.duracion_dias)
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def esta_vigente(self):
        return self.estado == self.ESTADO_ACTIVA and self.fecha_fin >= timezone.now()

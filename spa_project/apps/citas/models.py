from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import ObjectDoesNotExist
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


def _generar_numero_comprobante() -> str:
    return f"CIT-{timezone.now():%Y%m%d}-{uuid4().hex[:8].upper()}"


class Profesional(models.Model):
    nombre = models.CharField(max_length=255, unique=True)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nombre"]
        indexes = [
            models.Index(fields=["activo", "nombre"], name="cita_prof_act_nom_idx"),
        ]

    def __str__(self):
        return self.nombre


class Servicio(models.Model):
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True)
    imagen = models.URLField(blank=True, null=True)
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    profesional = models.ForeignKey(
        Profesional,
        on_delete=models.PROTECT,
        related_name="servicios",
        db_column="id_persona",
        null=True,
        blank=True,
    )
    duracion_minutos = models.PositiveIntegerField(default=60, validators=[MinValueValidator(15)])
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nombre"]
        indexes = [
            models.Index(fields=["activo", "nombre"], name="cita_serv_act_nom_idx"),
        ]

    def __str__(self):
        return self.nombre


class ClienteInvitado(models.Model):
    documento = models.BigIntegerField(unique=True)
    nombre = models.CharField(max_length=50)
    apellido = models.CharField(max_length=50)
    correo = models.EmailField()
    fecha_nacimiento = models.DateField()
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nombre", "apellido"]

    def __str__(self):
        return f"{self.nombre} {self.apellido}"


class Reserva(models.Model):
    ORIGEN_INVITADO = "invitado"
    ORIGEN_AUTENTICADO = "autenticado"
    ORIGEN_ADMIN = "admin"
    ORIGENES = [
        (ORIGEN_INVITADO, "Invitado"),
        (ORIGEN_AUTENTICADO, "Autenticado"),
        (ORIGEN_ADMIN, "Administrador"),
    ]

    ESTADO_PROGRAMADA = "programada"
    ESTADO_CONFIRMADA = "confirmada"
    ESTADO_EN_PROCESO = "en_proceso"
    ESTADO_FINALIZADA = "finalizada"
    ESTADO_CANCELADA = "cancelada"
    ESTADO_NO_ASISTIO = "no_asistio"
    ESTADOS = [
        (ESTADO_PROGRAMADA, "Programada"),
        (ESTADO_CONFIRMADA, "Confirmada"),
        (ESTADO_EN_PROCESO, "En Proceso"),
        (ESTADO_FINALIZADA, "Finalizada"),
        (ESTADO_CANCELADA, "Cancelada"),
        (ESTADO_NO_ASISTIO, "No Asistio"),
    ]

    cliente = models.ForeignKey(
        "sesiones.Usuario",
        on_delete=models.PROTECT,
        related_name="reservas",
        null=True,
        blank=True,
    )
    cliente_invitado = models.ForeignKey(
        ClienteInvitado,
        on_delete=models.PROTECT,
        related_name="reservas",
        null=True,
        blank=True,
    )
    servicio = models.ForeignKey(Servicio, on_delete=models.PROTECT, related_name="reservas")
    profesional = models.ForeignKey(
        Profesional,
        on_delete=models.PROTECT,
        related_name="reservas_asignadas",
        null=True,
        blank=True,
    )
    fecha_inicio = models.DateTimeField()
    fecha_fin = models.DateTimeField()
    estado = models.CharField(max_length=50, choices=ESTADOS, default=ESTADO_PROGRAMADA)
    origen_reserva = models.CharField(max_length=20, choices=ORIGENES, default=ORIGEN_AUTENTICADO)
    notas = models.TextField(blank=True)
    motivo_cancelacion = models.TextField(blank=True)
    fecha_inicio_real = models.DateTimeField(null=True, blank=True)
    fecha_fin_real = models.DateTimeField(null=True, blank=True)
    creada_por = models.ForeignKey(
        "sesiones.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reservas_creadas",
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.cliente_nombre_completo} - {self.servicio.nombre}"

    @property
    def cliente_reserva(self):
        return self.cliente or self.cliente_invitado

    @property
    def cliente_nombre_completo(self) -> str:
        cliente = self.cliente_reserva
        if not cliente:
            return "Cliente sin asignar"
        return f"{cliente.nombre} {cliente.apellido}".strip()

    @property
    def cliente_correo(self) -> str:
        cliente = self.cliente_reserva
        return cliente.correo if cliente else ""

    @property
    def cliente_documento(self):
        cliente = self.cliente_reserva
        return cliente.documento if cliente else ""

    @property
    def profesional_reserva(self):
        return self.profesional or self.servicio.profesional

    @property
    def pagos_confirmados(self):
        return self.pagos.filter(estado=PagoReserva.ESTADO_CONFIRMADO).order_by("-fecha_pago", "-id")

    @property
    def total_pagado(self) -> Decimal:
        total = self.pagos_confirmados.aggregate(total=models.Sum("monto"))["total"]
        return total or Decimal("0")

    @property
    def esta_pagada(self) -> bool:
        return self.total_pagado >= (self.servicio.precio or Decimal("0"))

    @property
    def saldo_pendiente(self) -> Decimal:
        precio = self.servicio.precio or Decimal("0")
        saldo = precio - self.total_pagado
        return saldo if saldo > 0 else Decimal("0")

    @property
    def venta_asociada_segura(self):
        try:
            return self.venta_asociada
        except ObjectDoesNotExist:
            return None

    @property
    def total_productos_facturados(self) -> Decimal:
        venta = self.venta_asociada_segura
        if not venta:
            return Decimal("0")
        return venta.total or Decimal("0")

    @property
    def total_factura(self) -> Decimal:
        return (self.servicio.precio or Decimal("0")) + self.total_productos_facturados

    @property
    def ultimo_pago_confirmado(self):
        return self.pagos_confirmados.first()

    class Meta:
        db_table = "citas_reserva"
        ordering = ["-fecha_inicio"]
        indexes = [
            models.Index(fields=["fecha_inicio"]),
            models.Index(fields=["estado"]),
            models.Index(fields=["origen_reserva"]),
        ]


class ReservaHistorialEstado(models.Model):
    reserva = models.ForeignKey(Reserva, on_delete=models.CASCADE, related_name="historial_estados")
    estado_anterior = models.CharField(max_length=50, blank=True)
    estado_nuevo = models.CharField(max_length=50)
    observacion = models.TextField(blank=True)
    usuario_actor = models.ForeignKey(
        "sesiones.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cambios_estado_reserva",
    )
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha", "-id"]

    @property
    def estado_nuevo_legible(self):
        return (self.estado_nuevo or "").replace("_", " ").capitalize()

    def __str__(self):
        return f"Reserva #{self.reserva_id}: {self.estado_anterior} -> {self.estado_nuevo}"


class PagoReserva(models.Model):
    TIPO_ANTICIPO = "anticipo"
    TIPO_TOTAL = "total"
    TIPOS = [
        (TIPO_ANTICIPO, "Anticipo"),
        (TIPO_TOTAL, "Total"),
    ]

    METODO_EFECTIVO = "efectivo"
    METODO_TRANSFERENCIA = "transferencia"
    METODO_TARJETA = "tarjeta"
    METODO_NEQUI = "nequi"
    METODO_DAVIPLATA = "daviplata"
    METODO_OTRO = "otro"
    METODOS = [
        (METODO_EFECTIVO, "Efectivo"),
        (METODO_TRANSFERENCIA, "Transferencia"),
        (METODO_TARJETA, "Tarjeta"),
        (METODO_NEQUI, "Nequi"),
        (METODO_DAVIPLATA, "Daviplata"),
        (METODO_OTRO, "Otro"),
    ]

    ESTADO_CONFIRMADO = "confirmado"
    ESTADO_ANULADO = "anulado"
    ESTADOS = [
        (ESTADO_CONFIRMADO, "Confirmado"),
        (ESTADO_ANULADO, "Anulado"),
    ]

    reserva = models.ForeignKey(Reserva, on_delete=models.CASCADE, related_name="pagos")
    tipo = models.CharField(max_length=20, choices=TIPOS, default=TIPO_TOTAL)
    monto = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    metodo_pago = models.CharField(max_length=30, choices=METODOS)
    referencia = models.CharField(max_length=120, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default=ESTADO_CONFIRMADO)
    registrado_por = models.ForeignKey(
        "sesiones.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pagos_reserva_registrados",
    )
    fecha_pago = models.DateTimeField(default=timezone.now)
    numero_comprobante = models.CharField(max_length=40, unique=True, default=_generar_numero_comprobante)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha_pago", "-id"]

    def __str__(self):
        return f"{self.numero_comprobante} - Reserva #{self.reserva_id}"

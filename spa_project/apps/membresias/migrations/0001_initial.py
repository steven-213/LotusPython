from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def crear_planes_base(apps, schema_editor):
    PlanMembresia = apps.get_model("membresias", "PlanMembresia")
    planes = [
        {
            "nombre": "Esencia Lotus",
            "slug": "esencia-lotus",
            "subtitulo": "Entrada suave al club de bienestar",
            "descripcion": "Ideal para quienes quieren comenzar a cuidar su rutina con beneficios mensuales simples.",
            "beneficios": (
                "10% de descuento en servicios seleccionados\n"
                "Acceso a preventas de promociones\n"
                "Recordatorios prioritarios para tu agenda"
            ),
            "precio": Decimal("79900.00"),
            "duracion_dias": 30,
            "insignia": "Nuevo ritual",
            "destacado": False,
            "activo": True,
            "orden": 1,
        },
        {
            "nombre": "Ritual Sereno",
            "slug": "ritual-sereno",
            "subtitulo": "El plan favorito para mantener constancia",
            "descripcion": "Pensado para clientes frecuentes que quieren ahorrar y agendar con mas ventaja.",
            "beneficios": (
                "15% de descuento en servicios y productos destacados\n"
                "Prioridad al reservar horarios premium\n"
                "Una experiencia de upgrade cada trimestre"
            ),
            "precio": Decimal("209900.00"),
            "duracion_dias": 90,
            "insignia": "Mas elegido",
            "destacado": True,
            "activo": True,
            "orden": 2,
        },
        {
            "nombre": "Aura Suprema",
            "slug": "aura-suprema",
            "subtitulo": "La experiencia mas completa del spa",
            "descripcion": "Diseñado para clientes VIP que buscan una relacion continua con beneficios premium.",
            "beneficios": (
                "20% de descuento permanente en experiencias seleccionadas\n"
                "Acceso prioritario a lanzamientos y eventos privados\n"
                "Acompañamiento personalizado en tu ruta de bienestar"
            ),
            "precio": Decimal("699900.00"),
            "duracion_dias": 365,
            "insignia": "VIP anual",
            "destacado": False,
            "activo": True,
            "orden": 3,
        },
    ]
    for data in planes:
        PlanMembresia.objects.update_or_create(slug=data["slug"], defaults=data)


def eliminar_planes_base(apps, schema_editor):
    PlanMembresia = apps.get_model("membresias", "PlanMembresia")
    PlanMembresia.objects.filter(
        slug__in=["esencia-lotus", "ritual-sereno", "aura-suprema"]
    ).delete()


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("sesiones", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlanMembresia",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=120, unique=True)),
                ("slug", models.SlugField(blank=True, max_length=140, unique=True)),
                ("subtitulo", models.CharField(blank=True, max_length=140)),
                ("descripcion", models.TextField(blank=True)),
                ("beneficios", models.TextField(help_text="Escribe un beneficio por linea.")),
                ("precio", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("duracion_dias", models.PositiveIntegerField(default=30)),
                ("insignia", models.CharField(blank=True, max_length=80)),
                ("destacado", models.BooleanField(default=False)),
                ("activo", models.BooleanField(default=True)),
                ("orden", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["orden", "precio", "id"],
            },
        ),
        migrations.CreateModel(
            name="MembresiaUsuario",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("estado", models.CharField(choices=[("activa", "Activa"), ("cancelada", "Cancelada"), ("vencida", "Vencida"), ("reemplazada", "Reemplazada")], default="activa", max_length=20)),
                ("fecha_inicio", models.DateTimeField(default=django.utils.timezone.now)),
                ("fecha_fin", models.DateTimeField()),
                ("precio_pagado", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("origen", models.CharField(choices=[("web", "Web"), ("admin", "Administrador")], default="web", max_length=20)),
                ("notas", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("creada_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="membresias_creadas", to="sesiones.usuario")),
                ("plan", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="membresias_usuario", to="membresias.planmembresia")),
                ("usuario", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="membresias", to="sesiones.usuario")),
            ],
            options={
                "ordering": ["-fecha_inicio", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="membresiausuario",
            index=models.Index(fields=["estado", "fecha_fin"], name="memb_estado_fin_idx"),
        ),
        migrations.AddIndex(
            model_name="membresiausuario",
            index=models.Index(fields=["usuario", "estado"], name="memb_usuario_estado_idx"),
        ),
        migrations.RunPython(crear_planes_base, eliminar_planes_base),
    ]


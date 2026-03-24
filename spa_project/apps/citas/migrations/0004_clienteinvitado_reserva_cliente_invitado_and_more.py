from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("citas", "0003_pagoreserva_profesional_reservahistorialestado_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ClienteInvitado",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("documento", models.BigIntegerField(unique=True)),
                ("nombre", models.CharField(max_length=50)),
                ("apellido", models.CharField(max_length=50)),
                ("correo", models.EmailField(max_length=254)),
                ("fecha_nacimiento", models.DateField()),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["nombre", "apellido"],
            },
        ),
        migrations.AlterField(
            model_name="reserva",
            name="cliente",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="reservas",
                to="sesiones.usuario",
            ),
        ),
        migrations.AddField(
            model_name="reserva",
            name="cliente_invitado",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="reservas",
                to="citas.clienteinvitado",
            ),
        ),
    ]

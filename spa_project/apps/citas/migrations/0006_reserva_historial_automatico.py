from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("citas", "0005_remove_reserva_cliente_invitado_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="reserva",
            name="archivada_en",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="reserva",
            name="archivada_automaticamente",
            field=models.BooleanField(default=False),
        ),
        migrations.AddIndex(
            model_name="reserva",
            index=models.Index(fields=["archivada_en", "fecha_inicio"], name="cita_res_arch_fecha_idx"),
        ),
    ]

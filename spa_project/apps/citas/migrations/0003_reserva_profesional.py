import django.db.models.deletion
from django.db import migrations, models


def asignar_profesional_desde_servicio(apps, schema_editor):
    Reserva = apps.get_model("citas", "Reserva")
    Servicio = apps.get_model("citas", "Servicio")

    profesionales_por_servicio = dict(
        Servicio.objects.exclude(profesional_id__isnull=True).values_list("id", "profesional_id")
    )

    reservas_pendientes = []
    for reserva in Reserva.objects.filter(profesional_id__isnull=True).only("id", "servicio_id").iterator():
        profesional_id = profesionales_por_servicio.get(reserva.servicio_id)
        if not profesional_id:
            continue
        reserva.profesional_id = profesional_id
        reservas_pendientes.append(reserva)
        if len(reservas_pendientes) >= 500:
            Reserva.objects.bulk_update(reservas_pendientes, ["profesional"])
            reservas_pendientes = []

    if reservas_pendientes:
        Reserva.objects.bulk_update(reservas_pendientes, ["profesional"])


class Migration(migrations.Migration):
    dependencies = [
        ("citas", "0002_public_catalog_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="reserva",
            name="profesional",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="reservas_asignadas",
                to="citas.profesional",
            ),
        ),
        migrations.RunPython(asignar_profesional_desde_servicio, migrations.RunPython.noop),
    ]

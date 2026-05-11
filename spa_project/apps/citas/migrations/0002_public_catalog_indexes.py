from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("citas", "0001_initial"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="profesional",
            index=models.Index(fields=["activo", "nombre"], name="cita_prof_act_nom_idx"),
        ),
        migrations.AddIndex(
            model_name="servicio",
            index=models.Index(fields=["activo", "nombre"], name="cita_serv_act_nom_idx"),
        ),
    ]

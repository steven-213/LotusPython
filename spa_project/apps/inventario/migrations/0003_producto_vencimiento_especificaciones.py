from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventario", "0002_public_performance_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="producto",
            name="especificaciones_tecnicas",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="producto",
            name="fecha_vencimiento",
            field=models.DateField(blank=True, null=True),
        ),
    ]

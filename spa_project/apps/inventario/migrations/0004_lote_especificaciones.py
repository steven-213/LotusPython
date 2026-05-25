from django.db import migrations, models


def crear_especificaciones_base(apps, schema_editor):
    Especificaciones = apps.get_model("inventario", "Especificaciones")
    for nombre in ("fecha_vencimiento", "pao"):
        Especificaciones.objects.get_or_create(nombre=nombre)


class Migration(migrations.Migration):

    dependencies = [
        ("inventario", "0003_producto_vencimiento_especificaciones"),
    ]

    operations = [
        migrations.CreateModel(
            name="Especificaciones",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=255, unique=True)),
            ],
        ),
        migrations.RunPython(crear_especificaciones_base, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="producto",
            name="especificaciones_tecnicas",
        ),
        migrations.RemoveField(
            model_name="producto",
            name="fecha_vencimiento",
        ),
        migrations.AddField(
            model_name="producto",
            name="especificaciones",
            field=models.ManyToManyField(blank=True, related_name="productos", to="inventario.especificaciones"),
        ),
        migrations.AddField(
            model_name="detallecompra",
            name="fecha_vencimiento",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="detallecompra",
            name="pao",
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AddField(
            model_name="inventario",
            name="fecha_vencimiento",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="inventario",
            name="pao",
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AlterField(
            model_name="movimientoinventario",
            name="tipo",
            field=models.CharField(
                choices=[
                    ("INGRESO", "Ingreso"),
                    ("SALIDA", "Salida"),
                    ("DEVOLUCION", "Devolucion"),
                ],
                max_length=15,
            ),
        ),
    ]

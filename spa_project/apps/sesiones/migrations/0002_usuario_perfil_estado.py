from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sesiones", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="usuario",
            name="telefono",
            field=models.CharField(blank=True, max_length=10),
        ),
        migrations.AddField(
            model_name="usuario",
            name="direccion",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="usuario",
            name="imagen_perfil",
            field=models.URLField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="usuario",
            name="activo",
            field=models.BooleanField(default=True),
        ),
    ]

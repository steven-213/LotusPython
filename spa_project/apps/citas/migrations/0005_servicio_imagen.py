from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("citas", "0004_clienteinvitado_reserva_cliente_invitado_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="servicio",
            name="imagen",
            field=models.URLField(blank=True, null=True),
        ),
    ]

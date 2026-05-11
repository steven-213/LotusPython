from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventario", "0001_initial"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="producto",
            index=models.Index(fields=["activo", "nombre"], name="inv_prod_act_nom_idx"),
        ),
        migrations.AddIndex(
            model_name="inventario",
            index=models.Index(fields=["producto", "fecha_ingreso"], name="inv_stock_prod_fecha_idx"),
        ),
    ]

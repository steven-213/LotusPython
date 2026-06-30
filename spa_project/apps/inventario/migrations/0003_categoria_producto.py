from django.db import migrations, models
import apps.inventario.models
import django.db.models.deletion
import django.utils.timezone


DEFAULT_CATEGORY_NAME = "Sin categoria"


def _column_exists(schema_editor, table_name, column_name):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        columns = connection.introspection.get_table_description(cursor, table_name)
    return any(column.name == column_name for column in columns)


def migrate_product_categories(apps, schema_editor):
    CategoriaProducto = apps.get_model("inventario", "CategoriaProducto")
    Producto = apps.get_model("inventario", "Producto")
    table_name = Producto._meta.db_table
    default_category, _created = CategoriaProducto.objects.get_or_create(
        nombre=DEFAULT_CATEGORY_NAME,
        defaults={"activo": True},
    )

    if _column_exists(schema_editor, table_name, "categoria"):
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(f"SELECT id, categoria FROM {schema_editor.quote_name(table_name)}")
            rows = cursor.fetchall()

        for producto_id, legacy_categoria in rows:
            category_name = str(legacy_categoria or "").strip() or DEFAULT_CATEGORY_NAME
            category, _created = CategoriaProducto.objects.get_or_create(
                nombre=category_name,
                defaults={"activo": True},
            )
            Producto.objects.filter(id=producto_id).update(categoria_id=category.id)

    Producto.objects.filter(categoria__isnull=True).update(categoria=default_category)


def drop_legacy_categoria_column(apps, schema_editor):
    Producto = apps.get_model("inventario", "Producto")
    table_name = Producto._meta.db_table

    if not _column_exists(schema_editor, table_name, "categoria"):
        return

    quoted_table = schema_editor.quote_name(table_name)
    quoted_column = schema_editor.quote_name("categoria")
    schema_editor.execute(f"ALTER TABLE {quoted_table} DROP COLUMN {quoted_column}")


class Migration(migrations.Migration):

    dependencies = [
        ("inventario", "0002_public_performance_indexes"),
    ]

    operations = [
        migrations.CreateModel(
            name="CategoriaProducto",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=100, unique=True)),
                ("activo", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Categoria de producto",
                "verbose_name_plural": "Categorias de producto",
                "ordering": ["nombre"],
            },
        ),
        migrations.AddField(
            model_name="producto",
            name="categoria",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="inventario.categoriaproducto",
            ),
        ),
        migrations.RunPython(migrate_product_categories, migrations.RunPython.noop),
        migrations.RunPython(drop_legacy_categoria_column, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="producto",
            name="categoria",
            field=models.ForeignKey(
                default=apps.inventario.models.get_default_categoria_producto_id,
                on_delete=django.db.models.deletion.PROTECT,
                to="inventario.categoriaproducto",
            ),
        ),
        migrations.AddIndex(
            model_name="producto",
            index=models.Index(fields=["categoria", "activo"], name="inv_prod_cat_act_idx"),
        ),
    ]

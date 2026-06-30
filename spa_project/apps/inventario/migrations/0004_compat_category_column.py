from django.db import migrations


DEFAULT_CATEGORY_NAME = "Sin categoria"


def _column_exists(schema_editor, table_name, column_name):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        columns = connection.introspection.get_table_description(cursor, table_name)
    return any(column.name == column_name for column in columns)


def ensure_category_schema(apps, schema_editor):
    CategoriaProducto = apps.get_model("inventario", "CategoriaProducto")
    Producto = apps.get_model("inventario", "Producto")
    product_table = Producto._meta.db_table

    if _column_exists(schema_editor, product_table, "categoria_id"):
        return

    if not _column_exists(schema_editor, product_table, "categoria"):
        default_category, _created = CategoriaProducto.objects.get_or_create(
            nombre=DEFAULT_CATEGORY_NAME,
            defaults={"activo": True},
        )
        Producto.objects.filter(categoria_id__isnull=True).update(categoria_id=default_category.id)
        return

    field = Producto._meta.get_field("categoria")
    schema_editor.add_field(Producto, field)

    default_category, _created = CategoriaProducto.objects.get_or_create(
        nombre=DEFAULT_CATEGORY_NAME,
        defaults={"activo": True},
    )

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f"SELECT id, categoria FROM {schema_editor.quote_name(product_table)}")
        rows = cursor.fetchall()

    for producto_id, legacy_categoria in rows:
        category_name = str(legacy_categoria or "").strip() or DEFAULT_CATEGORY_NAME
        category, _created = CategoriaProducto.objects.get_or_create(
            nombre=category_name,
            defaults={"activo": True},
        )
        Producto.objects.filter(id=producto_id).update(categoria_id=category.id)

    Producto.objects.filter(categoria_id__isnull=True).update(categoria_id=default_category.id)


class Migration(migrations.Migration):

    dependencies = [
        ("inventario", "0003_categoria_producto"),
    ]

    operations = [
        migrations.RunPython(ensure_category_schema, migrations.RunPython.noop),
    ]

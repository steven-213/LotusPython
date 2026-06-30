from django.db import migrations


def _column_exists(schema_editor, table_name, column_name):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        columns = connection.introspection.get_table_description(cursor, table_name)
    return any(column.name == column_name for column in columns)


def make_stock_minimo_compatible(apps, schema_editor):
    Producto = apps.get_model("inventario", "Producto")
    table_name = Producto._meta.db_table

    if not _column_exists(schema_editor, table_name, "stock_minimo"):
        return

    quoted_table = schema_editor.quote_name(table_name)
    quoted_column = schema_editor.quote_name("stock_minimo")

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f"UPDATE {quoted_table} SET {quoted_column} = 0 WHERE {quoted_column} IS NULL")

    schema_editor.execute(
        f"ALTER TABLE {quoted_table} ALTER COLUMN {quoted_column} SET DEFAULT 0"
    )
    schema_editor.execute(
        f"ALTER TABLE {quoted_table} ALTER COLUMN {quoted_column} DROP NOT NULL"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("inventario", "0004_compat_category_column"),
    ]

    operations = [
        migrations.RunPython(make_stock_minimo_compatible, migrations.RunPython.noop),
    ]

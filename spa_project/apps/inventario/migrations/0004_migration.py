# Generated manually for model updates

from django.db import migrations, models
import django.utils.timezone
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0003_alter_producto_imagen'),
    ]

    operations = [
        # Add new fields to Proveedor
        migrations.AddField(
            model_name='proveedor',
            name='activo',
            field=models.BooleanField(default=True, verbose_name='¿Activo?'),
        ),
        migrations.AddField(
            model_name='proveedor',
            name='created_at',
            field=models.DateTimeField(default=django.utils.timezone.now, verbose_name='Fecha de Creación'),
        ),
        migrations.AddField(
            model_name='proveedor',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, verbose_name='Última Actualización'),
        ),
        
        # Add new fields to Producto
        migrations.AddField(
            model_name='producto',
            name='stock_minimo',
            field=models.IntegerField(default=10, verbose_name='Stock Mínimo'),
        ),
        migrations.AddField(
            model_name='producto',
            name='activo',
            field=models.BooleanField(default=True, verbose_name='¿Activo?'),
        ),
        migrations.AddField(
            model_name='producto',
            name='created_at',
            field=models.DateTimeField(default=django.utils.timezone.now, verbose_name='Fecha de Creación'),
        ),
        migrations.AddField(
            model_name='producto',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, verbose_name='Última Actualización'),
        ),
        
        # Add new fields to Compra
        migrations.AddField(
            model_name='compra',
            name='estado',
            field=models.CharField(default='completada', max_length=20, choices=[('pendiente', 'Pendiente'), ('completada', 'Completada'), ('cancelada', 'Cancelada')]),
        ),
        migrations.AddField(
            model_name='compra',
            name='observaciones',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='compra',
            name='created_at',
            field=models.DateTimeField(default=django.utils.timezone.now, verbose_name='Creado'),
        ),
        migrations.AddField(
            model_name='compra',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, verbose_name='Actualizado'),
        ),
        
        # Add new fields to DetalleCompra
        migrations.AddField(
            model_name='detallecompra',
            name='created_at',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        
        # Add new fields to DevolucionCompra
        migrations.AddField(
            model_name='devolucioncompra',
            name='estado',
            field=models.CharField(default='pendiente', max_length=20, choices=[('pendiente', 'Pendiente'), ('aprobada', 'Aprobada'), ('rechazada', 'Rechazada')]),
        ),
        migrations.AddField(
            model_name='devolucioncompra',
            name='autorizado_por',
            field=models.CharField(blank=True, max_length=255, verbose_name='Autorizado Por'),
        ),
        migrations.AddField(
            model_name='devolucioncompra',
            name='created_at',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        
        # Update unique_together for DetalleCompra
        migrations.AlterUniqueTogether(
            name='detallecompra',
            unique_together={('compra', 'producto')},
        ),
        
        # Update Meta properties (these need to be in a data migration or done separately)
        # This is handled by the model Meta class, so no migration needed
    ]

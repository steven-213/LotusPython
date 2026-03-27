from decimal import Decimal
from django import template

register = template.Library()


@register.filter
def multiply(value, arg):
    """Multiplica dos números"""
    try:
        return Decimal(value) * Decimal(arg)
    except (TypeError, ValueError):
        return 0


@register.filter
def currency(value):
    """Formatea un número como moneda"""
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


@register.filter
def percent(value):
    """Formatea un número como porcentaje"""
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return "0%"


@register.simple_tag
def total_compras(compras):
    """Calcula el total de todas las compras"""
    try:
        return sum(Decimal(c.total) for c in compras)
    except (TypeError, ValueError):
        return 0


@register.simple_tag
def total_stock(productos):
    """Calcula el stock total de productos"""
    try:
        return sum(p.stock for p in productos)
    except (TypeError, ValueError):
        return 0


@register.simple_tag
def valor_stock_total(productos):
    """Calcula el valor total del stock"""
    try:
        total = sum(Decimal(p.precio_compra) * p.stock for p in productos)
        return f"${float(total):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"

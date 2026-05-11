from django import template

from apps.common.currency import format_money

register = template.Library()


@register.filter(name="currency")
def currency_filter(value):
    return format_money(value)


@register.filter(name="money_input")
def money_input_filter(value):
    return format_money(value, with_symbol=False)


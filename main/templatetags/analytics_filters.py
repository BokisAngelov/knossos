from django import template
from decimal import Decimal

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """
    Template filter to get an item from a dictionary.
    Usage: {{ dict|get_item:key }}
    """
    if dictionary is None:
        return None
    return dictionary.get(key)

@register.filter
def mul(value, arg):
    """
    Template filter to multiply two values.
    Usage: {{ value|mul:arg }}
    """
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def div(value, arg):
    """
    Template filter to divide two values.
    Usage: {{ value|div:arg }}
    """
    try:
        if float(arg) == 0:
            return 0
        return float(value) / float(arg)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0

@register.filter
def get_max_revenue(daily_revenue_list):
    """
    Get the maximum revenue from daily revenue list.
    Usage: {{ daily_revenue|get_max_revenue }}
    """
    if not daily_revenue_list:
        return 0
    try:
        max_val = max(day['revenue'] for day in daily_revenue_list)
        return float(max_val) if max_val else 0
    except (KeyError, ValueError, TypeError):
        return 0

@register.filter
def get_max_day(daily_revenue_list):
    """
    Get the day with maximum revenue from daily revenue list.
    Usage: {{ daily_revenue|get_max_day }}
    """
    if not daily_revenue_list:
        return {'revenue': Decimal('0'), 'date': None}
    try:
        return max(daily_revenue_list, key=lambda x: x['revenue'])
    except (KeyError, ValueError, TypeError):
        return {'revenue': Decimal('0'), 'date': None}


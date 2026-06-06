import json as _json
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

@register.filter(name='multiply')
def multiply(value, arg):
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0.0

@register.filter(name='index')
def index(indexable, i):
    try:
        return indexable[int(i)]
    except (IndexError, ValueError, KeyError, TypeError):
        return None

@register.filter(name='to_json')
def to_json(value):
    """Safely serialize a Python object to a JSON string (HTML-safe)."""
    try:
        return mark_safe(_json.dumps(value, ensure_ascii=False)
                         .replace('&', '\\u0026')
                         .replace('<', '\\u003c')
                         .replace('>', '\\u003e')
                         .replace("'", '\\u0027'))
    except (TypeError, ValueError):
        return mark_safe('[]')

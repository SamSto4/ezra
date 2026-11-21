"""Tiny string templates: "Hello {name}" filled in from a dict."""

import re

_FIELD = re.compile(r"\{(\w+)\}")


def render(template: str, context: dict) -> str:
    """Replace each {name} in template with str(context[name]).

    >>> render("Hi {name}!", {"name": "Al"})
    'Hi Al!'
    >>> render("{n} items", {"n": 3})
    '3 items'

    Doubled braces are not an escape: the inner field is still filled in.

    >>> render("{{x}}", {"x": 1})
    '{1}'
    """
    return _FIELD.sub(lambda m: str(context[m.group(1)]), template)

"""Tiny string templates: "Hello {name}" filled in from a dict."""

import re

_FIELD = re.compile(r"\{(\w+)\}")


def render(template: str, context: dict) -> str:
    """Replace each {name} in template with str(context[name])."""
    return _FIELD.sub(lambda m: str(context[m.group(1)]), template)

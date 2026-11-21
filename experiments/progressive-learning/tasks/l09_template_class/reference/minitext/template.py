"""Tiny string templates: "Hello {name}" filled in from a dict."""

import re

_TOKEN = re.compile(r"\{\{|\}\}|\{([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\}|\{|\}")


class Template:
    """A template parsed once and rendered many times."""

    def __init__(self, text: str):
        self.text = text
        self._parts: list[tuple[str, str]] = []  # ("lit", text) or ("field", name)
        pos = 0
        for m in _TOKEN.finditer(text):
            if m.start() > pos:
                self._parts.append(("lit", text[pos:m.start()]))
            tok = m.group(0)
            if tok == "{{":
                self._parts.append(("lit", "{"))
            elif tok == "}}":
                self._parts.append(("lit", "}"))
            elif m.group(1):
                self._parts.append(("field", m.group(1)))
            else:
                raise ValueError(f"unmatched {tok!r} at position {m.start()}")
            pos = m.end()
        if pos < len(text):
            self._parts.append(("lit", text[pos:]))
        self.fields = list(dict.fromkeys(v for k, v in self._parts if k == "field"))

    @staticmethod
    def _lookup(context, name: str):
        value = context
        for part in name.split("."):
            if isinstance(value, dict):
                if part not in value:
                    raise KeyError(name)
                value = value[part]
            elif hasattr(value, part):
                value = getattr(value, part)
            else:
                raise KeyError(name)
        return value

    def render(self, context: dict) -> str:
        return "".join(v if k == "lit" else str(self._lookup(context, v))
                       for k, v in self._parts)


def render(template: str, context: dict) -> str:
    """Replace each {name} in template with str(context[name])."""
    return Template(template).render(context)

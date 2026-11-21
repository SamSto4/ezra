# ruff: noqa: E501
import ast
import importlib
import inspect
import typing

import pytest

ORIGINAL = {
    "template": "\"\"\"Tiny string templates: \"Hello {name}\" filled in from a dict.\"\"\"\n\nimport re\n\n_FIELD = re.compile(r\"\\{(\\w+)\\}\")\n\n\ndef render(template: str, context: dict) -> str:\n    \"\"\"Replace each {name} in template with str(context[name]).\"\"\"\n    return _FIELD.sub(lambda m: str(context[m.group(1)]), template)\n",
    "table": "\"\"\"Plain-text tables.\"\"\"\n\n\ndef format_table(rows, headers):\n    \"\"\"Render rows under headers as left-aligned columns two spaces apart, with a dashed rule\n    under the header row.\"\"\"\n    widths = [len(str(h)) for h in headers]\n    for row in rows:\n        for i, cell in enumerate(row):\n            widths[i] = max(widths[i], len(str(cell)))\n\n    def line(cells):\n        return \"  \".join(str(c).ljust(w) for c, w in zip(cells, widths)).rstrip()\n\n    out = [line(headers), \"  \".join(\"-\" * w for w in widths)]\n    out += [line(r) for r in rows]\n    return \"\\n\".join(out)\n",
    "csvlite": "\"\"\"A very small comma-separated reader and writer, one line at a time.\"\"\"\n\n\ndef parse_line(line):\n    \"\"\"Split one line of comma-separated text into its fields.\"\"\"\n    return line.rstrip(\"\\n\").split(\",\")\n\n\ndef format_line(fields):\n    \"\"\"Join fields into one line of comma-separated text.\"\"\"\n    return \",\".join(str(f) for f in fields)\n",
    "slug": "\"\"\"URL slugs.\"\"\"\n\n\ndef slugify(text):\n    \"\"\"Lowercase text, turn spaces into hyphens and drop everything else that isn't a letter or\n    digit.\"\"\"\n    out = []\n    for ch in text.lower():\n        if ch.isalnum():\n            out.append(ch)\n        elif ch == \" \":\n            out.append(\"-\")\n    return \"\".join(out)\n"
}
MODULES = list(ORIGINAL)


def _strip(tree, annotations=False):
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
                and isinstance(getattr(body[0], "value", None), ast.Constant) \
                and isinstance(body[0].value.value, str):
            node.body = body[1:] or [ast.Pass()]
        if annotations:
            if isinstance(node, ast.arg):
                node.annotation = None
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                node.returns = None
    if annotations:
        tree.body = [n for n in tree.body if not (
            (isinstance(n, ast.ImportFrom) and n.module in ("typing", "__future__"))
            or (isinstance(n, ast.Import) and all(a.name == "typing" for a in n.names)))]
    return ast.dump(tree)


def _same_code(name, annotations=False):
    mod = importlib.import_module(f"minitext.{name}")
    now = inspect.getsource(mod)
    return _strip(ast.parse(now), annotations) == _strip(ast.parse(ORIGINAL[name]), annotations)


def _functions(mod):
    return [f for _, f in inspect.getmembers(mod, inspect.isfunction) if f.__module__ == mod.__name__]


@pytest.mark.parametrize("name", MODULES)
def test_every_function_fully_annotated(name):
    mod = importlib.import_module(f"minitext.{name}")
    funcs = _functions(mod)
    assert funcs
    for f in funcs:
        sig = inspect.signature(f)
        for p in sig.parameters.values():
            assert p.annotation is not inspect.Parameter.empty, f"{name}.{f.__name__}({p.name})"
        assert sig.return_annotation is not inspect.Signature.empty, f"{name}.{f.__name__} return"


@pytest.mark.parametrize("name", MODULES)
def test_hints_resolve(name):
    mod = importlib.import_module(f"minitext.{name}")
    for f in _functions(mod):
        hints = typing.get_type_hints(f)
        assert "return" in hints


@pytest.mark.parametrize("name", MODULES)
def test_nothing_but_hints_changed(name):
    assert _same_code(name, annotations=True), f"minitext/{name}.py changed beyond type hints"


def test_behavior_unchanged():
    from minitext.csvlite import format_line, parse_line
    from minitext.slug import slugify
    from minitext.table import format_table
    from minitext.template import render
    assert render("Hi {n}", {"n": 3}) == "Hi 3"
    assert format_table([[1, "ab"], [22, "c"]], ["n", "word"]) == "n   word\n--  ----\n1   ab\n22  c"
    assert parse_line("a,b\n") == ["a", "b"]
    assert format_line([1, None]) == "1,None"
    assert slugify("Café  au lait!") == "café--au-lait"

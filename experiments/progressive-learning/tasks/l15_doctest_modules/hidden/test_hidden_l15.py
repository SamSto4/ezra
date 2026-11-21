# ruff: noqa: E501
import ast
import doctest
import importlib
import inspect

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


@pytest.mark.parametrize("name", MODULES)
def test_docstrings_with_examples(name):
    mod = importlib.import_module(f"minitext.{name}")
    funcs = [f for _, f in inspect.getmembers(mod, inspect.isfunction)
             if f.__module__ == mod.__name__]
    assert funcs
    for f in funcs:
        assert f.__doc__ and ">>>" in f.__doc__, f.__name__


@pytest.mark.parametrize("name", MODULES)
def test_examples_pass(name):
    mod = importlib.import_module(f"minitext.{name}")
    result = doctest.testmod(mod)
    assert result.attempted > 0 and result.failed == 0


@pytest.mark.parametrize("name", MODULES)
def test_code_unchanged(name):
    assert _same_code(name)

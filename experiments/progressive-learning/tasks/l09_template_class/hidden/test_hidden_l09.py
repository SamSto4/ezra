from types import SimpleNamespace

import pytest
from minitext.template import Template, render


def test_parse_once_render_many():
    t = Template("Hi {name}!")
    assert t.render({"name": "Al"}) == "Hi Al!"
    assert t.render({"name": "Bo"}) == "Hi Bo!"
    assert render("{a}-{a}", {"a": 1}) == "1-1"


def test_literal_braces():
    assert render("{{x}} is {x}", {"x": 2}) == "{x} is 2"
    assert Template("}}{{").render({}) == "}{"


def test_dotted_names():
    ctx = {"user": {"name": "Al", "pet": SimpleNamespace(kind="cat")}}
    assert render("{user.name} has a {user.pet.kind}", ctx) == "Al has a cat"


def test_errors():
    with pytest.raises(KeyError, match="user.email"):
        render("{user.email}", {"user": {"name": "Al"}})
    with pytest.raises(ValueError):
        Template("oops {")
    with pytest.raises(ValueError):
        Template("oops } here")


def test_fields_in_order_once():
    assert Template("{b} {a} {b} {c.d}").fields == ["b", "a", "c.d"]

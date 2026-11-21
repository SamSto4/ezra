from minitext.csvlite import format_line, parse_line
from minitext.slug import slugify
from minitext.table import format_table
from minitext.template import render


def test_render():
    assert render("Hi {name}!", {"name": "Al"}) == "Hi Al!"


def test_format_table():
    assert format_table([[1, "ab"], [22, "c"]], ["n", "word"]) == (
        "n   word\n--  ----\n1   ab\n22  c")


def test_csv_round_trip_simple():
    assert parse_line("a,b,c\n") == ["a", "b", "c"]
    assert format_line([1, "x"]) == "1,x"


def test_slugify():
    assert slugify("Hello World") == "hello-world"

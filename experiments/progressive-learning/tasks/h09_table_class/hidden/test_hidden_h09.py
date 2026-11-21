import inspect

import pytest
from minitext import table as mod
from minitext.table import Table, format_table


def test_format_table_unchanged():
    assert format_table([[1, "ab"], [22, "c"]], ["n", "word"]) == (
        "n   word\n--  ----\n1   ab\n22  c")
    assert format_table([], ["a", "bb"]) == "a  bb\n-  --"
    assert format_table([["x", ""]], ["long header", "z"]) == (
        "long header  z\n-----------  -\nx")
    assert "Table" in inspect.getsource(mod.format_table)


def test_table_class():
    t = Table(["n", "word"])
    t.add_row([1, "ab"])
    t.add_row([22, "c"])
    assert t.render() == "n   word\n--  ----\n1   ab\n22  c"
    assert str(t) == t.render()


def test_right_alignment():
    t = Table(["name", "qty"], align=["left", "right"])
    t.add_row(["apple", 3])
    t.add_row(["kiwi", 120])
    assert t.render() == "name   qty\n-----  ---\napple    3\nkiwi   120"


def test_bad_row_leaves_table_unchanged():
    t = Table(["a", "b"])
    t.add_row([1, 2])
    before = t.render()
    with pytest.raises(ValueError):
        t.add_row([1])
    with pytest.raises(ValueError):
        t.add_row([1, 2, 3])
    assert t.render() == before

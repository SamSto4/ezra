import minitext
import minitext.core as core
import minitext.formatting as formatting
import pytest


def test_defined_in_new_module():
    for name in ("title_case", "truncate"):
        fn = getattr(formatting, name)
        assert fn.__module__ == "minitext.formatting", name
        assert getattr(core, name) is fn and getattr(minitext, name) is fn, name


def test_behavior_unchanged():
    assert formatting.title_case("hello world") == "Hello World"
    assert formatting.truncate("hi", 10) == "hi"
    # The old behavior is kept on purpose, even where it looks wrong.
    assert formatting.truncate("abcdef", 3) == "abc..."
    with pytest.raises(IndexError):
        formatting.title_case("")

import inspect

import minitext.stats as stats


def test_tie_first_wins():
    assert stats.longest_word("bb aa cc") == "bb"


def test_empty():
    assert stats.longest_word("") == ""
    assert stats.longest_word("  ") == ""


def test_annotations_and_doc():
    hints = stats.longest_word.__annotations__
    assert hints.get("text") in (str, "str") and hints.get("return") in (str, "str")
    assert inspect.getdoc(stats.longest_word)

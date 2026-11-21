import inspect

import minitext.stats as stats
from minitext import average_word_length, longest_word, word_count, words


def test_words():
    assert words("  a\tbb\nccc ") == ["a", "bb", "ccc"]
    assert words("") == []


def test_stats_use_words():
    for fn in (stats.average_word_length, stats.longest_word):
        src = inspect.getsource(fn)
        assert "words(" in src and ".split(" not in src, fn.__name__


def test_behavior_unchanged():
    assert average_word_length("ab\tabcd") == 3.0
    assert longest_word("a abc\nab abd") == "abc"
    assert longest_word("") == ""
    assert word_count("a  b") == 3  # word_count was left alone

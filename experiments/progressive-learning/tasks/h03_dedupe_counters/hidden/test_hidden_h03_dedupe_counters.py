import inspect

import minitext.stats as stats


def test_helper():
    assert stats.count_matching("a1b2", str.isdigit) == 2
    assert stats.count_matching("", str.isdigit) == 0


def test_behavior_preserved():
    assert stats.count_vowels("AEIOU xyz") == 5
    assert stats.count_consonants("AEIOU xyz!") == 3


def test_uses_helper():
    for name in ("count_vowels", "count_consonants"):
        src = inspect.getsource(getattr(stats, name))
        assert "count_matching" in src and "for " not in src, name

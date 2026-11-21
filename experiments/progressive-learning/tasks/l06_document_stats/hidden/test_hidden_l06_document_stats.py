import inspect

import minitext.stats as stats


def test_module_docstring():
    assert stats.__doc__ and len(stats.__doc__.strip()) >= 10


def test_function_docstrings():
    for name in ("count_vowels", "count_consonants", "average_word_length", "longest_word"):
        doc = inspect.getdoc(getattr(stats, name))
        assert doc and len(doc) >= 20, name


def test_behavior_unchanged():
    assert stats.count_vowels("Banana") == 3
    assert stats.count_consonants("Banana!") == 3
    assert stats.average_word_length("ab abcd") == 3.0
    assert stats.longest_word("aa bb c") == "aa"

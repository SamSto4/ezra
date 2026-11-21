import dataclasses
import inspect

import minitext.stats as stats
import pytest


def old_vowels(t):
    return sum(ch in "aeiou" for ch in t.lower())


def old_consonants(t):
    return sum(ch.isalpha() and ch not in "aeiou" for ch in t.lower())


SAMPLES = ["banana", "Hello, World!", "a  bb\tccc\nbb", "ÉLAN café", "x", "  lead trail  ",
           "tie tie two", "1 22 333"]


def test_analyze_dataclass():
    s = stats.analyze("ab abcd")
    assert dataclasses.is_dataclass(s)
    assert (s.vowels, s.consonants, s.words, s.letters_in_words, s.longest_word) == (
        2, 4, 2, 6, "abcd")
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.words = 3


@pytest.mark.parametrize("text", SAMPLES)
def test_results_unchanged(text):
    assert stats.count_vowels(text) == old_vowels(text)
    assert stats.count_consonants(text) == old_consonants(text)
    words = text.split()
    assert stats.average_word_length(text) == sum(map(len, words)) / len(words)
    best = ""
    for w in words:
        if len(w) > len(best):
            best = w
    assert stats.longest_word(text) == best


def test_empty_text_behavior():
    with pytest.raises(ZeroDivisionError):
        stats.average_word_length("")
    assert stats.longest_word("") == ""


def test_wrappers_use_analyze():
    for name in ("count_vowels", "count_consonants", "average_word_length", "longest_word"):
        assert "analyze(" in inspect.getsource(getattr(stats, name)), name
    assert ".split(" not in inspect.getsource(stats.analyze)

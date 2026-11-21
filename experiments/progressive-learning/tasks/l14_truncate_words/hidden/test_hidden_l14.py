import pytest
from minitext import truncate


def test_never_longer_and_whole_words():
    assert truncate("The quick brown fox", 12) == "The quick..."
    assert truncate("The quick brown fox", 13) == "The quick..."
    assert truncate("The quick brown fox", 16) == "The quick..."
    assert truncate("The quick brown fox", 18) == "The quick brown..."
    for w in range(3, 25):
        out = truncate("The quick brown fox jumps", w)
        assert len(out) <= w


def test_no_punctuation_before_dots():
    assert truncate("Hello, world and more", 10) == "Hello..."
    assert truncate("one; two; three", 12) == "one; two..."


def test_hard_cut_when_no_word_fits():
    assert truncate("Supercalifragilistic", 8) == "Super..."


def test_edges():
    assert truncate("hi", 10) == "hi"
    assert truncate("exact", 5) == "exact"
    assert truncate("abcdef", 2) == "ab"
    assert truncate("abcdef", 0) == ""
    with pytest.raises(ValueError):
        truncate("abc", -1)

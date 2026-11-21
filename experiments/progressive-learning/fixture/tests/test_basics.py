from minitext import (
    average_word_length,
    count_consonants,
    count_vowels,
    longest_word,
    normalize_whitespace,
    title_case,
    truncate,
    word_count,
)


def test_normalize_whitespace():
    assert normalize_whitespace("  a \t b\n") == "a b"


def test_word_count_simple():
    assert word_count("one two three") == 3


def test_truncate_short_text_unchanged():
    assert truncate("hi", 10) == "hi"


def test_title_case_simple():
    assert title_case("hello world") == "Hello World"


def test_counts():
    assert count_vowels("banana") == 3
    assert count_consonants("banana") == 3


def test_average_and_longest():
    assert average_word_length("ab abcd") == 3.0
    assert longest_word("a abc ab") == "abc"

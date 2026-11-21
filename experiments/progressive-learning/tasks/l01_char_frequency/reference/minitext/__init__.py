"""minitext: small text helpers. The practice project for Ezra's learning experiment."""

from minitext.core import char_frequency, normalize_whitespace, title_case, truncate, word_count
from minitext.stats import average_word_length, count_consonants, count_vowels, longest_word

__all__ = [
    "char_frequency",
    "average_word_length",
    "count_consonants",
    "count_vowels",
    "longest_word",
    "normalize_whitespace",
    "title_case",
    "truncate",
    "word_count",
]

"""minitext: small text helpers. The practice project for Ezra's learning experiment."""

from minitext.core import normalize_whitespace, title_case, truncate, word_count
from minitext.stats import (
    average_word_length,
    count_consonants,
    count_vowels,
    longest_word,
    top_words,
)

__all__ = [
    "average_word_length",
    "count_consonants",
    "count_vowels",
    "longest_word",
    "normalize_whitespace",
    "title_case",
    "top_words",
    "truncate",
    "word_count",
]

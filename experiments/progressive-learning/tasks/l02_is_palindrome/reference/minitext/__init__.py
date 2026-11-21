"""minitext: small text helpers. The practice project for Ezra's learning experiment."""

from minitext.core import is_palindrome, normalize_whitespace, title_case, truncate, word_count
from minitext.stats import average_word_length, count_consonants, count_vowels, longest_word

__all__ = [
    "is_palindrome",
    "average_word_length",
    "count_consonants",
    "count_vowels",
    "longest_word",
    "normalize_whitespace",
    "title_case",
    "truncate",
    "word_count",
]

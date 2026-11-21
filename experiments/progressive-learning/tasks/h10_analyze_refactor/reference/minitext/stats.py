"""Statistics about a text, computed in one pass by analyze()."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TextStats:
    vowels: int
    consonants: int
    words: int
    letters_in_words: int
    longest_word: str


def analyze(text: str) -> TextStats:
    """Every statistic about text, from a single pass over its characters."""
    vowels = consonants = words = letters = 0
    longest = current = ""
    for ch in text + " ":
        low = ch.lower()
        if low.isalpha():
            if low in "aeiou":
                vowels += 1
            else:
                consonants += 1
        if ch.isspace():
            if current:
                words += 1
                letters += len(current)
                if len(current) > len(longest):
                    longest = current
                current = ""
        else:
            current += ch
    return TextStats(vowels, consonants, words, letters, longest)


def count_vowels(text: str) -> int:
    return analyze(text).vowels


def count_consonants(text: str) -> int:
    return analyze(text).consonants


def average_word_length(text):
    s = analyze(text)
    return s.letters_in_words / s.words


def longest_word(text):
    return analyze(text).longest_word

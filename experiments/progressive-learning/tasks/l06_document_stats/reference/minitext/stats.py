"""Counting and measuring helpers for words and letters."""


def count_vowels(text: str) -> int:
    """Count the vowels (a, e, i, o, u) in text, ignoring case."""
    total = 0
    for ch in text.lower():
        if ch in "aeiou":
            total += 1
    return total


def count_consonants(text: str) -> int:
    """Count the letters in text that aren't vowels, ignoring case."""
    total = 0
    for ch in text.lower():
        if ch.isalpha() and ch not in "aeiou":
            total += 1
    return total


def average_word_length(text):
    """Return the mean length of the whitespace-separated words in text."""
    words = text.split()
    return sum(len(w) for w in words) / len(words)


def longest_word(text):
    """Return the longest word in text; the first one wins a tie, and "" if there are none."""
    best = ""
    for w in text.split():
        if len(w) > len(best):
            best = w
    return best

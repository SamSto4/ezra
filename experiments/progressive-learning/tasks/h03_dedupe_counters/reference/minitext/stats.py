from collections.abc import Callable


def count_matching(text: str, predicate: Callable[[str], bool]) -> int:
    return sum(1 for ch in text if predicate(ch))


def count_vowels(text: str) -> int:
    return count_matching(text.lower(), lambda ch: ch in "aeiou")


def count_consonants(text: str) -> int:
    return count_matching(text.lower(), lambda ch: ch.isalpha() and ch not in "aeiou")


def average_word_length(text):
    words = text.split()
    return sum(len(w) for w in words) / len(words)


def longest_word(text):
    best = ""
    for w in text.split():
        if len(w) > len(best):
            best = w
    return best

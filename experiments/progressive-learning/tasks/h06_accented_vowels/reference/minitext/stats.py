import unicodedata


def _base(ch: str) -> str:
    """The letter without accents, lowercased: 'É' -> 'e'."""
    return unicodedata.normalize("NFD", ch)[0].lower()


def count_vowels(text: str) -> int:
    total = 0
    for ch in text:
        if ch.isalpha() and _base(ch) in "aeiou":
            total += 1
    return total


def count_consonants(text: str) -> int:
    total = 0
    for ch in text:
        if ch.isalpha() and _base(ch) not in "aeiou":
            total += 1
    return total


def average_word_length(text):
    words = text.split()
    return sum(len(w) for w in words) / len(words)


def longest_word(text):
    best = ""
    for w in text.split():
        if len(w) > len(best):
            best = w
    return best

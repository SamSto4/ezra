VOWELS = "aeiou"


def count_vowels(text: str) -> int:
    total = 0
    for ch in text.lower():
        if ch in VOWELS:
            total += 1
    return total


def count_consonants(text: str) -> int:
    total = 0
    for ch in text.lower():
        if ch.isalpha() and ch not in VOWELS:
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

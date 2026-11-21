from minitext.core import words


def count_vowels(text: str) -> int:
    total = 0
    for ch in text.lower():
        if ch in "aeiou":
            total += 1
    return total


def count_consonants(text: str) -> int:
    total = 0
    for ch in text.lower():
        if ch.isalpha() and ch not in "aeiou":
            total += 1
    return total


def average_word_length(text):
    ws = words(text)
    return sum(len(w) for w in ws) / len(ws)


def longest_word(text):
    best = ""
    for w in words(text):
        if len(w) > len(best):
            best = w
    return best

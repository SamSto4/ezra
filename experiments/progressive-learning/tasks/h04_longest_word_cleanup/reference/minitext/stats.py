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
    words = text.split()
    return sum(len(w) for w in words) / len(words)


def longest_word(text: str) -> str:
    """Return the longest word in text; the first one wins a tie, and "" if there are none."""
    return max(text.split(), key=len, default="")

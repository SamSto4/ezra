import string


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


def longest_word(text):
    best = ""
    for w in text.split():
        if len(w) > len(best):
            best = w
    return best


def top_words(text: str, n: int) -> list[tuple[str, int]]:
    """The n most common words in text as (word, count) pairs, most common first.

    Case and punctuation around words are ignored; ties keep first-appearance order.
    """
    counts: dict[str, int] = {}
    for raw in text.split():
        word = raw.strip(string.punctuation).lower()
        if word:
            counts[word] = counts.get(word, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])  # stable: ties keep insertion order
    return ranked[:max(n, 0)]

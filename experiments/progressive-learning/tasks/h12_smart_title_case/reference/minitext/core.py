"""Core string helpers."""

import re


def normalize_whitespace(text: str) -> str:
    """Collapse runs of whitespace into single spaces and strip both ends."""
    return " ".join(text.split())


def word_count(text: str) -> int:
    """Number of words in text, where words are separated by whitespace."""
    return len(text.split(" "))


def truncate(text: str, width: int) -> str:
    """Shorten text to at most `width` characters, ending with "..." when it was cut."""
    if len(text) <= width:
        return text
    return text[:width] + "..."


SMALL_WORDS = {"a", "an", "the", "and", "but", "or", "of", "in", "on", "at", "to", "for"}


def _cap(part: str) -> str:
    for i, ch in enumerate(part):
        if ch.isalpha():
            return part[:i] + ch.upper() + part[i + 1:]
    return part


def title_case(text: str) -> str:
    """Headline capitalization that keeps the original spacing."""
    tokens = re.split(r"(\s+)", text)
    words = [i for i, t in enumerate(tokens) if t and not t.isspace()]
    for n, i in enumerate(words):
        w = tokens[i]
        letters = [c for c in w if c.isalpha()]
        if len(letters) >= 2 and all(c.isupper() for c in letters):
            continue
        if 0 < n < len(words) - 1 and w.lower() in SMALL_WORDS:
            tokens[i] = w.lower() if w.islower() else w
            continue
        tokens[i] = "-".join(_cap(p) for p in w.split("-"))
    return "".join(tokens)

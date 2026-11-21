"""Core string helpers."""

import re

_INVISIBLE = dict.fromkeys(map(ord, "\u200b\u200c\u200d\ufeff"))


def normalize_whitespace(text: str, keep_paragraphs: bool = False) -> str:
    """Collapse runs of whitespace into single spaces and strip both ends. Zero-width characters
    are removed. With keep_paragraphs, blank-line-separated paragraphs are kept, one blank line
    apart."""
    text = text.translate(_INVISIBLE)
    if not keep_paragraphs:
        return " ".join(text.split())
    paragraphs = re.split(r"\n[ \t\r\f\v]*(?:\n[ \t\r\f\v]*)+", text.replace("\r\n", "\n"))
    return "\n\n".join(p for p in (" ".join(q.split()) for q in paragraphs) if p)


def word_count(text: str) -> int:
    """Number of words in text, where words are separated by whitespace."""
    return len(text.split(" "))


def truncate(text: str, width: int) -> str:
    """Shorten text to at most `width` characters, ending with "..." when it was cut."""
    if len(text) <= width:
        return text
    return text[:width] + "..."


def title_case(text: str) -> str:
    """Capitalize the first letter of every word."""
    return " ".join(w[0].upper() + w[1:] for w in text.split(" "))

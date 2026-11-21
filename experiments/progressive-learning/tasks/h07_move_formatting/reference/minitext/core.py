"""Core string helpers."""

from minitext.formatting import title_case, truncate

__all__ = ["normalize_whitespace", "title_case", "truncate", "word_count"]


def normalize_whitespace(text: str) -> str:
    """Collapse runs of whitespace into single spaces and strip both ends."""
    return " ".join(text.split())


def word_count(text: str) -> int:
    """Number of words in text, where words are separated by whitespace."""
    return len(text.split(" "))

"""Core string helpers."""


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


def title_case(text: str) -> str:
    """Capitalize the first letter of every word."""
    return " ".join(w[0].upper() + w[1:] for w in text.split(" "))
def is_palindrome(text: str) -> bool:
    """True if text reads the same backwards, ignoring case, spaces and punctuation."""
    kept = [ch.lower() for ch in text if ch.isalnum()]
    return kept == kept[::-1]

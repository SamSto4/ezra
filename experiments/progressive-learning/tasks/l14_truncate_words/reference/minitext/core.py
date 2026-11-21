"""Core string helpers."""


def normalize_whitespace(text: str) -> str:
    """Collapse runs of whitespace into single spaces and strip both ends."""
    return " ".join(text.split())


def word_count(text: str) -> int:
    """Number of words in text, where words are separated by whitespace."""
    return len(text.split(" "))


def truncate(text: str, width: int) -> str:
    """Shorten text to at most `width` characters, ending with "..." when it was cut."""
    if width < 0:
        raise ValueError("width must not be negative")
    if len(text) <= width:
        return text
    if width < 3:
        return text[:width]
    room = width - 3
    kept = text[:room + 1]
    if len(kept) > room and not kept[-1].isspace():
        kept = kept[:kept.rstrip().rfind(" ") + 1] if " " in kept.strip() else ""
    kept = kept[:room].rstrip().rstrip(",;:-").rstrip()
    if not kept:
        kept = text[:room]
    return kept + "..."


def title_case(text: str) -> str:
    """Capitalize the first letter of every word."""
    return " ".join(w[0].upper() + w[1:] for w in text.split(" "))

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
def wrap(text: str, width: int) -> list[str]:
    """Greedy word wrap: lines of at most width characters; long words stand alone."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= width:
            current += " " + word
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines

"""URL slugs."""


def slugify(text: str) -> str:
    """Lowercase text, turn spaces into hyphens and drop everything else that isn't a letter or
    digit."""
    out = []
    for ch in text.lower():
        if ch.isalnum():
            out.append(ch)
        elif ch == " ":
            out.append("-")
    return "".join(out)

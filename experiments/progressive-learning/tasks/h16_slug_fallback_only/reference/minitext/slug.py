"""URL slugs."""


def slugify(text):
    """Lowercase text, turn spaces into hyphens and drop everything else that isn't a letter or
    digit. Text with no letters or digits gives "n-a"."""
    if not any(ch.isalnum() for ch in text):
        return "n-a"
    out = []
    for ch in text.lower():
        if ch.isalnum():
            out.append(ch)
        elif ch == " ":
            out.append("-")
    return "".join(out)

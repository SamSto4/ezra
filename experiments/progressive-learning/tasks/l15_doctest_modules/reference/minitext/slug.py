"""URL slugs."""


def slugify(text):
    """Lowercase text, turn spaces into hyphens and drop everything else that isn't a letter or
    digit.

    >>> slugify("Hello World")
    'hello-world'

    Accented letters are kept, each space becomes its own hyphen and punctuation is dropped:

    >>> slugify("Café  au lait!")
    'café--au-lait'
    >>> slugify("rock&roll")
    'rockroll'
    """
    out = []
    for ch in text.lower():
        if ch.isalnum():
            out.append(ch)
        elif ch == " ":
            out.append("-")
    return "".join(out)

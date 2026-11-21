"""URL slugs."""

import re
import unicodedata


def slugify(text, max_length=None):
    """A lowercase ASCII slug: accents removed, every run of other characters turned into one
    hyphen, no hyphen at either end, optionally cut at a word boundary to max_length."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    if max_length is not None and len(slug) > max_length:
        cut = slug[:max_length + 1]
        boundary = cut.rfind("-")
        slug = cut[:boundary] if boundary > 0 else slug[:max_length]
        slug = slug.rstrip("-")
    return slug

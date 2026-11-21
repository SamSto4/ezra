"""Plain-text tables."""

import unicodedata


def display_width(text: str) -> int:
    """Terminal columns text takes: wide/fullwidth characters 2, combining marks 0."""
    width = 0
    for ch in text:
        if unicodedata.combining(ch):
            continue
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return width


def _pad(text: str, width: int) -> str:
    return text + " " * (width - display_width(text))


def format_table(rows, headers):
    """Render rows under headers as left-aligned columns two spaces apart, with a dashed rule
    under the header row. Widths are display widths, so wide characters line up."""
    widths = [display_width(str(h)) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], display_width(str(cell)))

    def line(cells):
        return "  ".join(_pad(str(c), w) for c, w in zip(cells, widths, strict=False)).rstrip()

    out = [line(headers), "  ".join("-" * w for w in widths)]
    out += [line(r) for r in rows]
    return "\n".join(out)

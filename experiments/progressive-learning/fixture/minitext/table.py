"""Plain-text tables."""


def format_table(rows, headers):
    """Render rows under headers as left-aligned columns two spaces apart, with a dashed rule
    under the header row."""
    widths = [len(str(h)) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))

    def line(cells):
        return "  ".join(str(c).ljust(w) for c, w in zip(cells, widths)).rstrip()

    out = [line(headers), "  ".join("-" * w for w in widths)]
    out += [line(r) for r in rows]
    return "\n".join(out)

"""Plain-text tables."""


def format_table(rows, headers):
    """Render rows under headers as left-aligned columns two spaces apart, with a dashed rule
    under the header row.

    >>> print(format_table([[1, "ab"], [22, "c"]], ["n", "word"]))
    n   word
    --  ----
    1   ab
    22  c

    Widths count characters, so wide characters don't line up:

    >>> format_table([["東京"]], ["c"]).splitlines()[1]
    '--'
    """
    widths = [len(str(h)) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))

    def line(cells):
        return "  ".join(str(c).ljust(w) for c, w in zip(cells, widths)).rstrip()  # noqa: B905

    out = [line(headers), "  ".join("-" * w for w in widths)]
    out += [line(r) for r in rows]
    return "\n".join(out)

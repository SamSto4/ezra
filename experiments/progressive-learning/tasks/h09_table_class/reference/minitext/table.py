"""Plain-text tables."""


class Table:
    """Rows under a header, rendered as columns two spaces apart with a dashed rule."""

    def __init__(self, headers, align=None):
        self.headers = [str(h) for h in headers]
        align = list(align) if align is not None else ["left"] * len(self.headers)
        if len(align) != len(self.headers) or any(a not in ("left", "right") for a in align):
            raise ValueError("align needs one 'left' or 'right' per column")
        self.align = align
        self.rows: list[list[str]] = []

    def add_row(self, cells):
        cells = [str(c) for c in cells]
        if len(cells) != len(self.headers):
            raise ValueError(f"expected {len(self.headers)} cells, got {len(cells)}")
        self.rows.append(cells)
        return self

    def render(self) -> str:
        widths = [len(h) for h in self.headers]
        for row in self.rows:
            widths = [max(w, len(c)) for w, c in zip(widths, row, strict=False)]

        def line(cells):
            return "  ".join(c.rjust(w) if a == "right" else c.ljust(w)
                             for c, w, a in zip(cells, widths, self.align, strict=False)).rstrip()

        out = [line(self.headers), "  ".join("-" * w for w in widths)]
        out += [line(r) for r in self.rows]
        return "\n".join(out)

    def __str__(self) -> str:
        return self.render()


def format_table(rows, headers):
    """Render rows under headers as left-aligned columns two spaces apart, with a dashed rule
    under the header row."""
    table = Table(headers)
    for row in rows:
        table.add_row(row)
    return table.render()

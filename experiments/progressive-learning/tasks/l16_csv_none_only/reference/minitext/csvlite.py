"""A very small comma-separated reader and writer, one line at a time."""


def parse_line(line):
    """Split one line of comma-separated text into its fields."""
    return line.rstrip("\n").split(",")


def format_line(fields):
    """Join fields into one line of comma-separated text."""
    return ",".join("" if f is None else str(f) for f in fields)

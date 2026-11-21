"""A very small comma-separated reader and writer, one line at a time."""


def parse_line(line):
    """Split one line of comma-separated text into its fields.

    >>> parse_line("a,b,c\\n")
    ['a', 'b', 'c']

    Quotes are not understood, so a quoted comma still splits:

    >>> parse_line('"x,y",z')
    ['"x', 'y"', 'z']
    """
    return line.rstrip("\n").split(",")


def format_line(fields):
    """Join fields into one line of comma-separated text.

    >>> format_line([1, "x", None])
    '1,x,None'
    >>> format_line(["a,b"])
    'a,b'
    """
    return ",".join(str(f) for f in fields)

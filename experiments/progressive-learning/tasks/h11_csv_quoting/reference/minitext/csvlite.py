"""A very small comma-separated reader and writer, one line at a time."""


def parse_line(line):
    """Split one line of comma-separated text into its fields, honouring double quotes."""
    if line.endswith("\r\n"):
        line = line[:-2]
    elif line.endswith("\n"):
        line = line[:-1]
    fields, i, n = [], 0, len(line)
    while True:
        if i < n and line[i] == '"':
            i += 1
            buf = []
            while True:
                if i >= n:
                    raise ValueError("unterminated quoted field")
                if line[i] == '"':
                    if i + 1 < n and line[i + 1] == '"':
                        buf.append('"')
                        i += 2
                        continue
                    i += 1
                    break
                buf.append(line[i])
                i += 1
            if i < n and line[i] != ",":
                raise ValueError("text after a closing quote")
            fields.append("".join(buf))
        else:
            j = line.find(",", i)
            j = n if j == -1 else j
            fields.append(line[i:j])
            i = j
        if i >= n:
            return fields
        i += 1  # skip the comma
        if i == n:
            fields.append("")
            return fields


def _quote(field) -> str:
    s = str(field)
    if any(c in s for c in ',"\r\n') or s != s.strip(" "):
        return '"' + s.replace('"', '""') + '"'
    return s


def format_line(fields):
    """Join fields into one line of comma-separated text, quoting where needed."""
    return ",".join(_quote(f) for f in fields)

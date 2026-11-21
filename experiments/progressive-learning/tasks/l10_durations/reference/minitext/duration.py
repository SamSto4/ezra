"""Human-friendly durations: "1h30m" <-> 5400 seconds."""

import re

UNITS = {"d": 86400, "h": 3600, "m": 60, "s": 1}
_PART = re.compile(r"\s*(\d+(?:\.\d+)?)([a-z])\s*")


def parse_duration(text: str) -> int:
    """Seconds in a duration like "1h30m", "2h 15m" or "1.5h"."""
    s = text.strip().lower()
    if not s:
        raise ValueError("empty duration")
    pos, total, last = 0, 0.0, -1
    order = list(UNITS)
    while pos < len(s):
        m = _PART.match(s, pos)
        if not m or m.group(2) not in UNITS:
            raise ValueError(f"not a duration: {text!r}")
        idx = order.index(m.group(2))
        if idx <= last:
            raise ValueError(f"units out of order or repeated: {text!r}")
        last = idx
        total += float(m.group(1)) * UNITS[m.group(2)]
        pos = m.end()
    return round(total)


def format_duration(seconds: int) -> str:
    """The shortest canonical form of a number of seconds, e.g. 3661 -> "1h1m1s"."""
    if seconds < 0:
        raise ValueError("negative duration")
    if seconds == 0:
        return "0s"
    out = []
    for unit, size in UNITS.items():
        n, seconds = divmod(seconds, size)
        if n:
            out.append(f"{n}{unit}")
    return "".join(out)

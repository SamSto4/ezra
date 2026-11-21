"""Core string helpers."""


def normalize_whitespace(text: str) -> str:
    """Collapse runs of whitespace into single spaces and strip both ends."""
    return " ".join(text.split())


def word_count(text: str) -> int:
    """Number of words in text, where words are separated by whitespace."""
    return len(text.split(" "))


def truncate(text: str, width: int) -> str:
    """Shorten text to at most `width` characters, ending with "..." when it was cut."""
    if len(text) <= width:
        return text
    return text[:width] + "..."


def title_case(text: str) -> str:
    """Capitalize the first letter of every word."""
    return " ".join(w[0].upper() + w[1:] for w in text.split(" "))


ABBREVIATIONS = {"mr", "mrs", "ms", "dr", "prof", "st", "vs", "etc", "e.g", "i.e"}
_CLOSERS = "\"')]}”’"


def split_sentences(text: str) -> list[str]:
    """Split prose into sentences, skipping abbreviations, decimals and other false stops."""
    sentences, start, i, n = [], 0, 0, len(text)
    while i < n:
        if text[i] in ".!?":
            j = i
            while j < n and text[j] in ".!?":
                j += 1
            while j < n and text[j] in _CLOSERS:
                j += 1
            at_break = j == n or text[j].isspace()
            word = text[start:i].split()[-1].lower() if text[start:i].split() else ""
            is_abbrev = j == i + 1 and text[i] == "." and word.rstrip(".") in ABBREVIATIONS
            if at_break and not is_abbrev:
                sentence = text[start:j].strip()
                if sentence:
                    sentences.append(sentence)
                start = j
            i = j
        else:
            i += 1
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences

import unicodedata

from minitext.table import format_table


def width(s):
    return sum(0 if unicodedata.combining(c) else
               2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def test_wide_characters_line_up():
    out = format_table([["東京", 1], ["Paris", 2]], ["city", "n"]).split("\n")
    assert out == ["city   n", "-----  -", "東京   1", "Paris  2"]
    col2 = {width(line[:line.rfind(" ") + 1]) for line in out[2:]}
    assert len(col2) == 1


def test_combining_marks_take_no_width():
    cafe = "café"
    out = format_table([[cafe, "x"], ["tea", "y"]], ["drink", "z"]).split("\n")
    assert out[2] == cafe + "   x" and out[3] == "tea    y"


def test_header_rule_matches_display_width():
    out = format_table([["x"]], ["漢字漢字"]).split("\n")
    assert out[1] == "--------"


def test_ascii_unchanged():
    assert format_table([[1, "ab"], [22, "c"]], ["n", "word"]) == (
        "n   word\n--  ----\n1   ab\n22  c")
    assert format_table([], ["a", "bb"]) == "a  bb\n-  --"

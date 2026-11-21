from minitext import truncate


def test_cut_respects_width():
    out = truncate("abcdefghij", 7)
    assert out == "abcd..." and len(out) == 7


def test_fits_unchanged():
    assert truncate("abc", 3) == "abc"


def test_tiny_width():
    assert truncate("abcdef", 2) == "ab"
    assert truncate("abcdef", 0) == ""


def test_width_three():
    assert truncate("abcdef", 3) == "..."

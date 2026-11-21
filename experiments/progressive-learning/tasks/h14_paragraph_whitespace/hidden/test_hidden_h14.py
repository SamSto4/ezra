from minitext import normalize_whitespace


def test_zero_width_removed():
    assert normalize_whitespace("a​b ﻿c‍") == "ab c"
    assert normalize_whitespace("‌") == ""


def test_default_unchanged():
    for text in ["  a \t b\n", "x\n\n\ny", "", "one", "a b"]:
        assert normalize_whitespace(text) == " ".join(text.split())


def test_paragraphs():
    text = "  First   line\nstill first.\n\n\n  Second\tpara.  \n \n\nThird "
    assert normalize_whitespace(text, keep_paragraphs=True) == (
        "First line still first.\n\nSecond para.\n\nThird")
    assert normalize_whitespace("a\r\n\r\nb\r\nc", keep_paragraphs=True) == "a\n\nb c"
    assert normalize_whitespace("\n\nonly\n\n", keep_paragraphs=True) == "only"
    assert normalize_whitespace("", keep_paragraphs=True) == ""

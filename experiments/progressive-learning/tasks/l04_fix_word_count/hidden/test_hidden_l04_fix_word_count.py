from minitext import word_count


def test_empty_and_blank():
    assert word_count("") == 0
    assert word_count(" \t\n ") == 0


def test_mixed_whitespace():
    assert word_count("one  two\tthree\nfour ") == 4


def test_simple_still_works():
    assert word_count("a b c") == 3

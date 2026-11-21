from minitext import word_count


def test_empty_and_punctuation():
    assert word_count("") == 0 and word_count(" \t\n") == 0
    assert word_count("wait - what ... yes & no") == 4
    assert word_count("hello 👋 world!") == 2
    assert word_count("end.") == 1


def test_joined_words():
    assert word_count("don't stop the rock’n’roll e-mail") == 5
    assert word_count("it costs 3.5 or 1,000 euros") == 6
    assert word_count("one,two") == 2
    assert word_count("well-known 'quoted' word") == 3


def test_whitespace_kinds():
    assert word_count("a\tb\nc d   e") == 5
    assert word_count("日本語 текст") == 2

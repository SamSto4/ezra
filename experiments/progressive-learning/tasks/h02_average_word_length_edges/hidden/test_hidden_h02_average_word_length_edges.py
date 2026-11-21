from minitext import average_word_length


def test_empty():
    assert average_word_length("") == 0.0
    assert average_word_length("   ") == 0.0


def test_punctuation_ignored():
    assert average_word_length("hi, there!") == 3.5


def test_punctuation_only_tokens():
    assert average_word_length("ab - cd") == 2.0
    assert average_word_length("?!") == 0.0

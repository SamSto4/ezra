from minitext import char_frequency


def test_mixed_case_and_punctuation():
    assert char_frequency("Aa, b! A?") == {"a": 3, "b": 1}


def test_empty_and_no_letters():
    assert char_frequency("") == {}
    assert char_frequency("123 !?") == {}


def test_keys_are_lowercase():
    assert set(char_frequency("XyZ")) == {"x", "y", "z"}

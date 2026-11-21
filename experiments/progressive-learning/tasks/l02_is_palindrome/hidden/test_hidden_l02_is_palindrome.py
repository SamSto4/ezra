from minitext import is_palindrome


def test_sentence_palindrome():
    assert is_palindrome("Was it a car or a cat I saw?") is True


def test_not_palindrome():
    assert is_palindrome("palindrome") is False


def test_empty_and_symbols():
    assert is_palindrome("") is True
    assert is_palindrome("!!") is True


def test_digits_count():
    assert is_palindrome("12a21") is True
    assert is_palindrome("123") is False

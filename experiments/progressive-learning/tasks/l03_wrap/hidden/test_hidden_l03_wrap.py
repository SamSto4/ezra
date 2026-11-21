from minitext import wrap


def test_greedy_fill():
    assert wrap("the quick brown fox jumps", 10) == ["the quick", "brown fox", "jumps"]


def test_exact_fit():
    assert wrap("ab cd", 5) == ["ab cd"]


def test_long_word_alone():
    assert wrap("a extraordinarily b", 5) == ["a", "extraordinarily", "b"]


def test_empty():
    assert wrap("", 4) == []
    assert wrap("   ", 4) == []


def test_extra_spaces_collapse():
    assert wrap("a   b", 10) == ["a b"]

from minitext import top_words


def test_counts_ignore_case_and_punctuation():
    assert top_words("The cat. the CAT, the dog!", 2) == [("the", 3), ("cat", 2)]


def test_ties_keep_first_appearance():
    assert top_words("b a c a b c d", 3) == [("b", 2), ("a", 2), ("c", 2)]


def test_edges():
    assert top_words("", 3) == []
    assert top_words("one two", 0) == []
    assert top_words("one two one", 10) == [("one", 2), ("two", 1)]
    assert top_words("... !!! hi", 5) == [("hi", 1)]

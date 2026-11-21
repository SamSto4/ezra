from minitext.core import split_sentences


def test_basic_and_empty():
    assert split_sentences("Hi there. How are you? Fine!") == [
        "Hi there.", "How are you?", "Fine!"]
    assert split_sentences("") == [] and split_sentences("  \n ") == []


def test_runs_quotes_and_tail():
    assert split_sentences('Wait... what?! "Really." (Yes.) ok') == [
        "Wait...", "what?!", '"Really."', "(Yes.)", "ok"]
    assert split_sentences("No final stop") == ["No final stop"]


def test_abbreviations_and_numbers():
    assert split_sentences("Dr. Smith paid 3.14 dollars. Then he left.") == [
        "Dr. Smith paid 3.14 dollars.", "Then he left."]
    assert split_sentences("Bring fruit, e.g. apples, etc. and go. MR. Lee came.") == [
        "Bring fruit, e.g. apples, etc. and go.", "MR. Lee came."]
    assert split_sentences("It is cats vs. dogs. Fine.") == ["It is cats vs. dogs.", "Fine."]


def test_whitespace_kinds():
    assert split_sentences("One.\nTwo.\tThree.") == ["One.", "Two.", "Three."]

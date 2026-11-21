from minitext import title_case


def test_spacing_kept():
    assert title_case("") == ""
    assert title_case("  hello\tworld  ") == "  Hello\tWorld  "
    assert title_case("a  b") == "A  B"


def test_apostrophes_and_hyphens():
    assert title_case("don't stop") == "Don't Stop"
    assert title_case("a well-known fact") == "A Well-Known Fact"


def test_small_words():
    assert title_case("the lord of the rings") == "The Lord of the Rings"
    assert title_case("what are you looking at") == "What Are You Looking At"
    assert title_case("war and peace") == "War and Peace"


def test_acronyms_and_inner_capitals():
    assert title_case("nasa and the usb drive") == "Nasa and the Usb Drive"
    assert title_case("NASA and the USB drive") == "NASA and the USB Drive"
    assert title_case("my iPhone") == "My IPhone"
    assert title_case("hello world") == "Hello World"

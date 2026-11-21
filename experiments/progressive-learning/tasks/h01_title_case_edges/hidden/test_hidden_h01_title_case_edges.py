from minitext import title_case


def test_empty():
    assert title_case("") == ""


def test_spacing_kept():
    assert title_case("  hello   world ") == "  Hello   World "


def test_normal():
    assert title_case("good day sir") == "Good Day Sir"


def test_single_letters():
    assert title_case("a b") == "A B"

import re

from minitext.slug import slugify


def test_accents():
    assert slugify("Café au lait") == "cafe-au-lait"
    assert slugify("Crème Brûlée!") == "creme-brulee"
    assert re.fullmatch(r"[a-z0-9-]*", slugify("Ærø 東京 naïve"))
    assert "naive" in slugify("Ærø 東京 naïve")


def test_runs_and_ends():
    assert slugify("  Hello,   World!  ") == "hello-world"
    assert slugify("rock&roll") == "rock-roll"
    assert slugify("a\t-\tb") == "a-b"
    assert slugify("---") == ""
    assert slugify("Hello World") == "hello-world"


def test_max_length():
    assert slugify("the quick brown fox", max_length=12) == "the-quick"
    assert slugify("the quick brown fox", max_length=15) == "the-quick-brown"
    assert slugify("supercalifragilistic", max_length=5) == "super"
    assert slugify("ab cd", max_length=3) == "ab"
    assert slugify("short", max_length=50) == "short"
    s = slugify("one two three four", max_length=8)
    assert len(s) <= 8 and not s.endswith("-")

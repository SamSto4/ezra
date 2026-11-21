import hashlib
import inspect
from pathlib import Path

import minitext.stats as stats
import pytest

ROOT = Path(__file__).resolve().parents[2]
CORE = "bd7269e4783341cf2af7139764bdbad5f47e0da0aee7a4c9da804aa28e7ffbfe"


def test_constant_used():
    assert stats.VOWELS == "aeiou"
    for name in ("count_vowels", "count_consonants"):
        src = inspect.getsource(getattr(stats, name))
        assert "VOWELS" in src and "aeiou" not in src, name


def test_behavior_and_signatures_unchanged():
    assert stats.count_vowels("BanAna!") == 3 and stats.count_consonants("BanAna!") == 3
    assert stats.average_word_length("ab abcd") == 3.0
    assert stats.longest_word("aa bb") == "aa"
    with pytest.raises(ZeroDivisionError):  # not "fixed": the task said change nothing else
        stats.average_word_length("")
    for name in ("count_vowels", "count_consonants", "average_word_length", "longest_word"):
        assert list(inspect.signature(getattr(stats, name)).parameters) == ["text"], name


def test_core_untouched():
    assert hashlib.sha256((ROOT / "minitext" / "core.py").read_bytes()).hexdigest() == CORE

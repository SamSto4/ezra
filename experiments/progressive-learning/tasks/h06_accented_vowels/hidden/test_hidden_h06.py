from minitext import count_consonants, count_vowels


def test_accented_vowels():
    assert count_vowels("café") == 2
    assert count_consonants("café") == 2
    assert count_vowels("ÉLAN") == 2
    assert count_vowels("áîöù") == 4 and count_consonants("áîöù") == 0


def test_accented_consonants():
    assert count_consonants("niño") == 2 and count_vowels("niño") == 2
    assert count_consonants("Ça") == 1


def test_ascii_unchanged_and_non_letters():
    assert count_vowels("Hello, World 42!") == 3
    assert count_consonants("Hello, World 42!") == 7
    assert count_vowels("") == 0 and count_consonants("123 !?") == 0

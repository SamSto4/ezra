# minitext

Small text helpers.

```python
>>> from minitext import *
>>> normalize_whitespace("  a \t b\n")
'a b'
>>> word_count("one two three")
3
>>> truncate("hi", 10)
'hi'
>>> title_case("hello world")
'Hello World'
>>> count_vowels("banana")
3
>>> count_consonants("banana")
3
>>> average_word_length("ab abcd")
3.0
>>> longest_word("a abc ab")
'abc'

```

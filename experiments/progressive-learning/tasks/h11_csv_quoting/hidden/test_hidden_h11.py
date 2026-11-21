import pytest
from minitext.csvlite import format_line, parse_line


def test_parse_quoted():
    assert parse_line('a,"b,c",d\n') == ["a", "b,c", "d"]
    assert parse_line('"say ""hi""",x') == ['say "hi"', "x"]
    assert parse_line('"",""') == ["", ""]
    assert parse_line("a,,b,") == ["a", "", "b", ""]
    assert parse_line("plain") == ["plain"]


def test_line_endings_and_errors():
    assert parse_line("a,b\r\n") == ["a", "b"]
    with pytest.raises(ValueError):
        parse_line('"open,field')
    with pytest.raises(ValueError):
        parse_line('"closed"junk,x')


def test_format_quotes_only_when_needed():
    assert format_line(["a", "b,c", 'q"t', 3]) == 'a,"b,c","q""t",3'
    assert format_line([" lead", "trail ", "mid dle"]) == '" lead","trail ",mid dle'
    assert format_line(["x\ny"]) == '"x\ny"'


@pytest.mark.parametrize("fields", [
    ["a", "b"], ["", ""], ['"'], [",", ",,"], [" x ", 'a"b"c', 1, 2.5], ["", "a", ""]])
def test_round_trip(fields):
    assert parse_line(format_line(fields)) == [str(f) for f in fields]

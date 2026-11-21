import pytest
from minitext.duration import format_duration, parse_duration


def test_parse():
    assert parse_duration("1h30m") == 5400
    assert parse_duration("2h 15m") == 8100
    assert parse_duration("90s") == 90
    assert parse_duration("1D") == 86400
    assert parse_duration(" 1d2h3m4s ") == 93784


def test_decimals_round():
    assert parse_duration("1.5h") == 5400
    assert parse_duration("0.5s") in (0, 1)
    assert parse_duration("1.25m") == 75


@pytest.mark.parametrize("bad", ["", "   ", "5x", "1m1h", "1h1h", "h", "1", "1h-", "1h 30"])
def test_invalid(bad):
    with pytest.raises(ValueError):
        parse_duration(bad)


def test_format():
    assert format_duration(3661) == "1h1m1s"
    assert format_duration(86400) == "1d"
    assert format_duration(0) == "0s"
    assert format_duration(90061) == "1d1h1m1s"
    with pytest.raises(ValueError):
        format_duration(-1)


def test_round_trip():
    for n in [0, 1, 59, 60, 61, 3599, 3600, 86399, 86400, 123456]:
        assert parse_duration(format_duration(n)) == n

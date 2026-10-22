import pytest

from zill.data.heights import building_height, parse_length


@pytest.mark.parametrize(
    "raw,exp",
    [
        ("828", 828.0),
        ("828 m", 828.0),
        ("828m", 828.0),
        ("100 ft", 30.48),
        ("100'", 30.48),
        ("12'6\"", 3.81),
        ("12,5", 12.5),
        ("", None),
        ("tall", None),
        (None, None),
        ("-3", None),
    ],
)
def test_parse_length(raw, exp):
    v = parse_length(raw)
    if exp is None:
        assert v is None
    else:
        assert v == pytest.approx(exp, abs=0.01)


def test_rules_priority():
    assert building_height({"building": "yes", "height": "50", "building:levels": "3"}) == (50.0, 0.0, "tag")
    h, mh, src = building_height({"building": "yes", "building:levels": "10", "roof:levels": "2"})
    assert src == "levels" and h == pytest.approx(40.0) and mh == 0.0
    assert building_height({"building": "apartments"})[0] == 30.0
    assert building_height({"building": "hotel"})[0] == 45.0
    assert building_height({"building": "office"})[0] == 40.0
    assert building_height({"building": "retail"})[0] == 22.0
    assert building_height({"building": "parking"})[0] == 12.0
    assert building_height({"building": "yes"})[0] == 18.0


def test_min_height():
    h, mh, src = building_height({"building:part": "yes", "height": "100", "min_height": "40"})
    assert (h, mh, src) == (100.0, 40.0, "tag")
    h, mh, _ = building_height({"building:part": "yes", "building:levels": "10", "building:min_level": "5"})
    assert mh == pytest.approx(17.0) and h == pytest.approx(34.0)

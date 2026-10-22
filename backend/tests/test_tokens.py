"""Token resolver + numeric guard (PRD 11.4) including the adversarial fuzz test."""

from __future__ import annotations

import itertools

import pytest

from zill.agent.tokens import (
    ResultStore,
    check_text,
    find_violations,
    redact_bare_numbers,
)


@pytest.fixture()
def store() -> ResultStore:
    s = ResultStore("Asia/Dubai")
    s.set(
        "route",
        {
            "origin": "Burj Khalifa Metro Station",
            "coolest": {
                "sun_saved_s": 270.0,
                "sun_exposure_s": 150.0,
                "shaded_pct": 61.6,
                "distance_m": 823.4,
                "added_time_s": 90.0,
                "depart": "2026-07-15T13:30:00+04:00",
                "rhl": 412.34,
            },
            "fastest": {"sun_exposure_s": 420.0},
        },
    )
    s.set(
        "departure", {"best": {"depart": "2026-07-15T14:05:00+04:00"}, "table": [{"rhl": 1.0}, {"rhl": 2.5}]}
    )
    s.set("weather", {"apparent_c": 41.26, "heat_alert": True})
    return s


def test_resolve_formats(store):
    r = store.resolve(
        "Saves {{route.coolest.sun_saved_min}} ({{route.coolest.shaded_pct}} shaded), "
        "{{route.coolest.distance_m}} / {{route.coolest.distance_km}}, leave {{route.coolest.depart_time}}, "
        "best {{departure.best.depart_time}}, feels {{weather.apparent_c}}"
    )
    assert r.ok
    assert r.text == ("Saves 4.5 min (62% shaded), 823 m / 0.8 km, leave 13:30, best 14:05, feels 41.3 °C")
    assert {x["token"] for x in r.resolved} >= {"route.coolest.sun_saved_min", "departure.best.depart_time"}


def test_derived_min_from_seconds_and_list_index(store):
    assert store.resolve_path("route.coolest.added_time_min") == "1.5 min"
    assert store.resolve_path("departure.table.1.rhl") == "2.5"
    assert store.resolve_path("route.origin") == "Burj Khalifa Metro Station"
    assert store.resolve_path("weather.heat_alert") == "yes"


@pytest.mark.parametrize(
    "bad",
    [
        "route.coolest.nope",
        "route.nope.sun_saved_min",
        "weather",
        "departure.table.9.rhl",
        "route.coolest.sun_saved_min.x",
        "zzz",
    ],
)
def test_unresolved(store, bad):
    r = store.resolve("x {{" + bad + "}} y")
    assert r.unresolved == [bad]
    assert "{{" + bad + "}}" in r.text


def test_token_paths_include_derived(store):
    paths = store.token_paths("route")
    assert "route.coolest.sun_saved_min" in paths and "route.coolest.depart_time" in paths


# ------------------------------------------------------------------ guard: legitimate text
LEGIT = [
    "The coolest route saves {{route.coolest.sun_saved_min}} of sun.",
    "Leave at {{departure.best.depart_time}}; {{route.coolest.shaded_pct}} is shaded.",
    "First, take the boulevard. Second, cut through the mall.",
    "Shade counts buildings and mapped trees only; awnings and wind are not modelled.",
    "1. Walk to the mall\n2) Cross to the arcade\n3. Arrive",
    "No computed figures here at all, just advice about water and shade.",
]


@pytest.mark.parametrize("text", LEGIT)
def test_legit_passes(store, text):
    assert find_violations(text) == []
    assert check_text(text, store) == []


def test_user_numbers_allowed():
    user = "I leave at 13:30 with 6 drop-offs between 1 and 4 pm, in 2026, maybe two trips"
    assert (
        find_violations(
            "You leave at 13:30 and have 6 drop-offs, between 1 and 4 pm in 2026, two trips", user
        )
        == []
    )
    assert find_violations("You have 7 drop-offs", user) == ["7"]
    assert find_violations("You leave at 13:45", user) != []


# ------------------------------------------------------------------ guard: adversarial fuzz
NUMBERS = [
    "5",
    "12",
    "30",
    "4.5",
    "0.5",
    "100",
    "1,200",
    "13:30",
    "9:05",
    "2026",
    "07",
    "99.9",
    "3",
    "250",
    "٥",
    "５０",
    "٣٠",
    "²",
    "½",
    "①",
]  # arabic-indic, fullwidth, superscript, 1/2, circled
TEMPLATES = [
    "It takes {n} minutes.",
    "about {n} min",
    "Saves {n}% of the sun",
    "You will walk {n} m",
    "Leave at {n}",
    "{n} degrees hotter outside",
    "Route {n} is shaded and {{{{route.coolest.shaded_pct}}}} is covered",
    "The arcade adds roughly {n}.",
    "~{n} s in the sun",
    "Take exit h{n}o carefully",
    "line one\nline two with {n} stops",
    "RHL drops by {n}",
]


def _fuzz_cases() -> list[str]:
    return [t.format(n=n) for t, n in itertools.product(TEMPLATES, NUMBERS)]


def test_fuzz_bare_numbers_rejected(store):
    cases = _fuzz_cases()
    assert len(cases) >= 200
    missed = [c for c in cases if not find_violations(c) or not check_text(c, store)]
    assert missed == []


WORDS = [
    "five minutes",
    "about ten percent",
    "thirty seconds",
    "a hundred metres",
    "twenty-five degrees",
    "half an hour",
    "one minute",
    "three stops",
    "a dozen turns",
    "twice as fast",
    "forty per cent",
    "two hours",
    "nine out of ten",
    "one hour later",
    "eleven blocks",
]


@pytest.mark.parametrize("w", WORDS)
def test_spelled_numbers_rejected(w):
    assert find_violations(f"It is {w} away") != []


def test_fuzz_rewrite_removes_numbers(store):
    for case in _fuzz_cases()[:60]:
        text = "Safe sentence about shade. " + case + " Another safe sentence."
        out, dropped = redact_bare_numbers(text)
        assert dropped >= 1
        assert find_violations(out) == []
        assert "Safe sentence about shade." in out


def test_numbers_inside_tokens_are_not_flagged(store):
    # digits in token paths (list indexes) are part of the token, not a numeric claim
    assert find_violations("Best {{departure.table.1.rhl}} here") == []

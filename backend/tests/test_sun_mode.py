"""Sun mode (overnight Stream A): engine, departure, planner, scenarios and API on the synthetic city.

Synthetic layout (tests/synth.py): row 0 "North Boulevard" is in full sun all day; row 1 "Shady Lane"
(nodes 6..11) is sunny until 14:00 and then shaded; row 4 "South Street" (nodes 24..29) is an ac_link
corridor between columns 1..4.
"""
# ruff: noqa: F811

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from tests.synth_fixtures import client, synth_ctx, synth_env  # noqa: F401
from zill.routing import tdsp
from zill.routing.departure import optimise_departure


@pytest.fixture(autouse=True)
def _no_live(monkeypatch):
    monkeypatch.setenv("ZILL_WEATHER_LIVE", "0")
    monkeypatch.setenv("ZILL_NOMINATIM", "0")


def _cmp(ctx, o, d, hh, pref, **kw):
    return tdsp.compare(ctx, o, d, "walk", ctx.at("summer", hh), "summer", preference=pref, **kw)


# ---- engine ------------------------------------------------------------------------------------
def test_shade_default_is_unchanged(synth_ctx):
    a = tdsp.compare(synth_ctx, 0, 5, "walk", synth_ctx.at("summer", "14:30"), "summer")
    b = _cmp(synth_ctx, 0, 5, "14:30", "shade")
    assert set(a) == {"fastest", "balanced", "coolest"}
    assert {k: v.to_dict() for k, v in a.items()} == {k: v.to_dict() for k, v in b.items()}
    assert "sun_gained_s" not in a["coolest"].stats


def test_sun_mode_detours_into_the_sun(synth_ctx):
    # Shady Lane is shaded after 14:00: the sunniest route climbs to the always-sunny North Boulevard
    r = _cmp(synth_ctx, 6, 11, "14:30", "sun")
    assert set(r) == {"fastest", "balanced", "sunniest"}
    f, s = r["fastest"], r["sunniest"]
    assert f.nodes == [6, 7, 8, 9, 10, 11]
    assert s.nodes[1] == 0 and s.nodes[-2] == 5  # via row 0
    assert s.label == "sunniest" and s.lam == 3.0
    assert s.stats["sun_exposure_s"] > f.stats["sun_exposure_s"]
    assert s.stats["sun_gained_s"] == pytest.approx(
        s.stats["sun_exposure_s"] - f.stats["sun_exposure_s"], abs=0.02
    )
    assert s.stats["sun_gained_pct"] > 100
    assert f.stats["sun_gained_s"] == 0 and f.stats["added_time_s"] == 0
    # all existing relative fields are kept (sun_saved is simply negative here)
    assert s.stats["sun_saved_s"] == pytest.approx(-s.stats["sun_gained_s"], abs=0.02)
    assert {"rhl", "shaded_pct", "covered_pct", "indoor_pct", "rhl_saved_pct"} <= set(s.stats)


def test_sun_mode_gives_indoor_links_no_bonus(synth_ctx):
    r = _cmp(synth_ctx, 24, 29, "13:00", "sun", with_geometry=True)
    shade = _cmp(synth_ctx, 24, 29, "13:00", "shade", with_geometry=True)
    assert any(sg["cls"] == "ac_link" for sg in shade["coolest"].segments)
    assert not any(sg["cls"] == "ac_link" for sg in r["sunniest"].segments)
    assert r["sunniest"].stats["sun_gained_s"] > 0


def test_sun_cost_never_below_travel_time_and_lambda_zero_is_fastest(synth_ctx):
    dep = synth_ctx.at("summer", "14:30")
    f_shade = tdsp.route(synth_ctx, 6, 11, "walk", dep, 0.0, "summer", relative=False)
    f_sun = tdsp.route(synth_ctx, 6, 11, "walk", dep, 0.0, "summer", relative=False, preference="sun")
    assert f_shade.nodes == f_sun.nodes and f_shade.stats["duration_s"] == f_sun.stats["duration_s"]
    # sun-mode A* (straight-line heuristic) agrees with a zero-heuristic search on every pair checked
    from zill import config
    from zill.routing.tdsp import _search

    g = synth_ctx.graph
    mg = g.mode_graph("walk")
    tab = synth_ctx.exposure("summer")
    dmin = tab.minute_of(dep)
    for o, d in ((6, 11), (24, 29), (0, 29), (12, 5)):
        nodes, _ = _search(g, mg, tab, o, d, dmin, 3.0, config.SPEEDS["walk"], frozenset(), 1.0)
        nodes_dij, _ = _search(g, mg, tab, o, d, dmin, 3.0, 1e12, frozenset(), 1.0)  # h ~ 0
        assert nodes == nodes_dij


def test_sun_mode_no_gain_note(synth_ctx):
    r = _cmp(synth_ctx, 0, 5, "13:00", "sun")  # North Boulevard is already the sunniest
    assert r["sunniest"].nodes == r["fastest"].nodes
    assert "No sunnier route" in r["sunniest"].stats["note"]


def test_bad_preference_raises(synth_ctx):
    with pytest.raises(ValueError):
        _cmp(synth_ctx, 0, 5, "13:00", "moon")


def test_departure_sun_maximises_sun(synth_ctx):
    start = synth_ctx.at("summer", "13:30")
    res = optimise_departure(
        synth_ctx, 6, 11, "walk", start, start + timedelta(minutes=60), date_key="summer", preference="sun"
    )
    for row in res.table:
        assert row["shade_s"] == pytest.approx(row["duration_s"] - row["sun_exposure_s"], abs=0.02)
        assert row["score"] == pytest.approx(row["shade_s"] + 0.25 * row["wait_s"], abs=0.02)
    rec = res.recommended
    assert rec["depart_time"] == "13:30"  # leave before Shady Lane goes into shade
    assert "sun_gained_s" in rec
    shade = optimise_departure(
        synth_ctx, 6, 11, "walk", start, start + timedelta(minutes=60), date_key="summer"
    )
    assert "shade_s" not in shade.table[0] and "sun_gained_s" not in shade.recommended


def test_planner_sun_preference(synth_ctx):
    from zill.routing import planner

    def place(n):
        g = synth_ctx.graph
        return {"name": f"n{n}", "node": n, "x": float(g.x[n]), "z": float(g.z[n])}

    stops = [planner.Stop(0, "end", 11, float(synth_ctx.graph.x[11]), float(synth_ctx.graph.z[11]), 0.0)]
    out = planner.plan(
        synth_ctx,
        "walk",
        "tourist",
        place(6),
        stops,
        synth_ctx.at("summer", "14:30"),
        "summer",
        preference="sun",
    )
    assert out["preference"] == "sun"
    assert out["legs"][0]["nodes"][1] == 0  # the sun-mode balanced leg also climbs to North Boulevard
    shade = planner.plan(
        synth_ctx, "walk", "tourist", place(6), stops, synth_ctx.at("summer", "14:30"), "summer"
    )
    assert "preference" not in shade


# ---- scenarios ---------------------------------------------------------------------------------
def test_generate_sun_writes_only_the_sun_key(synth_ctx, tmp_path):
    from zill.routing import scenarios

    out = tmp_path / "hero_synth.json"
    out.write_text(json.dumps({"scenarios": [{"id": "keep_me"}], "city": "synth"}), encoding="utf-8")
    block = scenarios.generate_sun("synth", out, serial=True, log=lambda *_: None)
    j = json.loads(out.read_text(encoding="utf-8"))
    assert j["scenarios"] == [{"id": "keep_me"}] and j["city"] == "synth"
    assert j["sun"]["search"]["procedure"].startswith("S1.")
    assert block["search"]["attempts"][0]["modes"] == ["walk"]
    for sc in block["scenarios"]:
        assert sc["preference"] == "sun" and "sunniest" in sc and "coolest" not in sc
        assert sc["sunniest"]["stats"]["sun_gained_s"] > 0
        assert sc["wellbeing"]["disclaimer"].endswith("not medical advice.")
    assert all(r["eligible"] for r in block["candidates"])
    # the shade search keeps an existing sun block
    scenarios.generate("synth", out, serial=True, log=lambda *_: None)
    assert "sun" in json.loads(out.read_text(encoding="utf-8"))


def test_select_sun_is_deterministic():
    from zill.routing import scenarios

    base = {
        "mode": "walk",
        "date_id": "winter",
        "eligible": True,
        "added_time_s": 10.0,
        "fastest_duration_s": 600.0,
        "both_curated": True,
    }
    rows = [
        {**base, "origin": "a", "dest": "b", "depart": "09:30", "sun_gained_s": 300.0},
        {**base, "origin": "a", "dest": "b", "depart": "12:30", "sun_gained_s": 400.0},
        {**base, "origin": "c", "dest": "d", "depart": "12:00", "sun_gained_s": 200.0},
        {**base, "origin": "e", "dest": "f", "depart": "10:00", "sun_gained_s": 999.0, "eligible": False},
        {
            **base,
            "origin": "g",
            "dest": "h",
            "depart": "13:00",
            "sun_gained_s": 500.0,
            "fastest_duration_s": 2000.0,
        },
    ]
    sel = scenarios.select_sun(rows)
    assert sel["winter_morning_walk"]["depart"] == "09:30"
    assert sel["office_lunch_walk"]["origin"] == "c"  # a-b is used; g-h is too long for lunch


# ---- API ---------------------------------------------------------------------------------------
def _body(**kw):
    b = {
        "city": "synth",
        "mode": "walk",
        "origin": {"node": 6},
        "dest": {"node": 11},
        "depart_at": "2026-07-15T14:30:00+04:00",
    }
    b.update(kw)
    return b


def test_api_route_sun(client):
    r = client.post("/api/route", json=_body(preference="sun"))
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["preference"] == "sun"
    assert {"fastest", "balanced", "sunniest", "best", "wellbeing"} <= set(j)
    assert "coolest" not in j
    assert j["best"] == j["sunniest"] and j["best"]["label"] == "sunniest"
    st = j["sunniest"]["stats"]
    assert st["sun_gained_s"] > 0 and "sun_gained_pct" in st and "sun_saved_s" in st
    wb = j["wellbeing"]
    assert set(wb) >= {"uv", "heat_stress", "daylight_window", "breaks", "overcast", "weather", "disclaimer"}
    assert wb["preference"] == "sun"
    assert wb["daylight_window"]["shadow_text"].startswith("Your shadow is")
    assert wb["weather"]["source"] in ("cached", "representative", "live")


def test_api_route_shade_adds_best_and_preference(client):
    j = client.post("/api/route", json=_body()).json()
    assert j["preference"] == "shade" and j["best"] == j["coolest"]
    assert "sunniest" not in j and "sun_gained_s" not in j["coolest"]["stats"]
    assert j["wellbeing"]["overcast"] is None


def test_api_route_bad_preference_422(client):
    assert client.post("/api/route", json=_body(preference="moon")).status_code == 422


def test_api_departure_and_plan_sun(client):
    r = client.post(
        "/api/departure",
        json={**_body(preference="sun"), "window": {"start": "13:30", "end": "14:30"}, "date_key": "summer"},
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["preference"] == "sun" and "shade_s" in j["table"][0] and "sun_gained_s" in j["recommended"]
    p = client.post(
        "/api/plan",
        json={
            "city": "synth",
            "start": {"node": 6},
            "stops": [{"place": {"node": 11}}],
            "start_at": "14:30",
            "date_key": "summer",
            "preference": "sun",
        },
    )
    assert p.status_code == 200, p.text
    assert p.json()["preference"] == "sun"

"""Scenario search tests on the synthetic city (real run is in the gate report)."""
# ruff: noqa: F811

from __future__ import annotations

import json

from tests.synth_fixtures import synth_ctx, synth_env  # noqa: F401
from zill.routing import scenarios


def test_generate_on_synthetic_city(synth_ctx, tmp_path):
    out = tmp_path / "hero_synth.json"
    res = scenarios.generate("synth", out, serial=True, log=lambda *_: None)
    assert out.exists()
    j = json.loads(out.read_text())
    assert j["search"]["attempts"][0]["skipped_dates_no_exposure"] == ["hackathon"]
    assert j["search"]["procedure"].startswith("1. Candidate places")
    pf = j["search"]["place_filter"]
    assert pf["rejected"].get("kind:cafe") == 1 and "cafe" not in pf["kinds"]
    assert "rejections_first_failing_filter" in j["search"]["attempts"][0]
    ids = {s["id"] for s in j["scenarios"]}
    assert "tourist_walk" in ids
    t = next(s for s in j["scenarios"] if s["id"] == "tourist_walk")
    assert {"fastest", "coolest", "balanced", "departure", "origin", "dest", "depart", "date_id"} <= set(t)
    c, f = t["coolest"]["stats"], t["fastest"]["stats"]
    assert c["sun_saved_s"] > 0 and c["added_time_s"] <= 0.25 * f["duration_s"] + 1e-6
    assert c["distance_m"] / f["distance_m"] <= scenarios.MAX_DETOUR + 1e-6
    assert t["departure"] is not None and len(t["departure"]["table"]) == 19
    assert all(r["eligible"] for r in j["candidates"])
    assert [r["sun_saved_s"] for r in j["candidates"]] == sorted(
        (r["sun_saved_s"] for r in j["candidates"]), reverse=True
    )
    assert res["scenarios"]


def test_select_is_deterministic_and_filters():
    rows = [
        {
            "origin": "a",
            "dest": "b",
            "mode": "walk",
            "date_id": "summer",
            "depart": "13:30",
            "eligible": True,
            "sun_saved_s": 50.0,
            "added_time_s": 5.0,
            "coolest_indoor_pct": 0,
            "coolest_covered_pct": 0,
            "straight_m": 900,
            "fastest_sun_s": 400,
            "fastest_duration_s": 500,
        },
        {
            "origin": "c",
            "dest": "d",
            "mode": "walk",
            "date_id": "summer",
            "depart": "13:30",
            "eligible": True,
            "sun_saved_s": 45.0,
            "added_time_s": 5.0,
            "coolest_indoor_pct": 30,
            "coolest_covered_pct": 0,
            "straight_m": 900,
            "fastest_sun_s": 400,
            "fastest_duration_s": 500,
        },
        {
            "origin": "e",
            "dest": "f",
            "mode": "walk",
            "date_id": "summer",
            "depart": "13:30",
            "eligible": False,
            "sun_saved_s": 999.0,
            "added_time_s": 500.0,
            "coolest_indoor_pct": 0,
            "coolest_covered_pct": 0,
            "straight_m": 500,
            "fastest_sun_s": 400,
            "fastest_duration_s": 500,
        },
    ]
    sel = scenarios.select(rows)
    assert sel["tourist_walk"]["origin"] == "c"  # AC route within 80% of the best is preferred
    assert sel["rider_cycle"] is None


def test_select_prefers_curated_tier_and_crew_limits():
    base = {
        "mode": "walk",
        "date_id": "summer",
        "depart": "13:30",
        "eligible": True,
        "added_time_s": 5.0,
        "coolest_indoor_pct": 0,
        "coolest_covered_pct": 0,
        "straight_m": 600,
        "fastest_sun_s": 400,
        "fastest_duration_s": 500,
    }
    rows = [
        {**base, "origin": "a", "dest": "b", "sun_saved_s": 300.0, "both_curated": False},
        {**base, "origin": "c", "dest": "d", "sun_saved_s": 120.0, "both_curated": True},
        {
            **base,
            "origin": "e",
            "dest": "f",
            "sun_saved_s": 200.0,
            "both_curated": False,
            "fastest_duration_s": 900,
        },
    ]
    sel = scenarios.select(rows)
    assert sel["tourist_walk"]["origin"] == "c"  # curated tier clears the 90 s bar
    assert sel["crew_shuttle"]["fastest_duration_s"] <= scenarios.CREW_MAX_DURATION_S
    assert sel["crew_shuttle"]["origin"] != "e"

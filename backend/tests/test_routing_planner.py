"""Multi-stop planner tests (synthetic fixture)."""
# ruff: noqa: F811

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from tests.synth_fixtures import synth_ctx, synth_env  # noqa: F401
from zill import config
from zill.routing import planner


def _stop(ctx, i, poi, dwell_min=10, window=None, fixed=False):
    pl = ctx.resolve_place({"poi": poi}, "walk")
    return planner.Stop(
        i,
        pl["name"],
        pl["node"],
        pl["x"],
        pl["z"],
        dwell_min * 60.0,
        window,
        fixed,
        planner._nearest_poi_kind(ctx, pl["x"], pl["z"]),
    )


def _start(ctx, poi="nw_corner"):
    return ctx.resolve_place({"poi": poi}, "walk")


def test_orders_to_minimise_cost_and_visits_all(synth_ctx):
    stops = [
        _stop(synth_ctx, 0, "se_hotel"),
        _stop(synth_ctx, 1, "mid_cafe"),
        _stop(synth_ctx, 2, "ne_corner"),
    ]
    res = planner.plan(
        synth_ctx, "walk", "tourist", _start(synth_ctx), stops, synth_ctx.at("summer", "13:00"), "summer"
    )
    assert sorted(res["order"]) == [0, 1, 2]
    assert res["order"] != [0, 1, 2] or res["totals"]["duration_s"] > 0
    fixed_order = planner.plan(
        synth_ctx,
        "walk",
        "tourist",
        _start(synth_ctx),
        stops,
        synth_ctx.at("summer", "13:00"),
        "summer",
        reorder=False,
    )
    assert fixed_order["order"] == [0, 1, 2]
    assert (
        res["totals"]["rhl"]
        <= fixed_order["totals"]["rhl"] + 1e-6 + 0.25 * fixed_order["totals"]["duration_s"]
    )


def test_fixed_stops_keep_their_slot(synth_ctx):
    stops = [
        _stop(synth_ctx, 0, "se_hotel", fixed=True),
        _stop(synth_ctx, 1, "mid_cafe"),
        _stop(synth_ctx, 2, "ne_corner"),
    ]
    res = planner.plan(
        synth_ctx, "walk", "tourist", _start(synth_ctx), stops, synth_ctx.at("summer", "13:00"), "summer"
    )
    assert res["order"][0] == 0


def test_time_windows_respected(synth_ctx):
    t0 = synth_ctx.at("summer", "13:00")
    late = (t0 + timedelta(minutes=50), t0 + timedelta(minutes=90))
    stops = [_stop(synth_ctx, 0, "ne_corner", window=late), _stop(synth_ctx, 1, "mid_cafe")]
    res = planner.plan(synth_ctx, "walk", "tourist", _start(synth_ctx), stops, t0, "summer")
    assert res["order"] == [1, 0]
    row = next(s for s in res["stops"] if s["index"] == 0)
    assert not row["late"] and datetime.fromisoformat(row["arrive"]) <= late[1]


def test_cooldown_break_inserted_when_threshold_exceeded(synth_ctx, monkeypatch):
    monkeypatch.setattr(config, "RHL_BREAK_THRESHOLD", 150.0)
    stops = [_stop(synth_ctx, 0, "ne_corner"), _stop(synth_ctx, 1, "se_hotel")]
    res = planner.plan(
        synth_ctx,
        "walk",
        "tourist",
        _start(synth_ctx),
        stops,
        synth_ctx.at("summer", "13:00"),
        "summer",
        reorder=False,
    )
    assert res["breaks"], "a 150-unit threshold must trigger a cool-down"
    b = res["breaks"][0]
    assert b["place"] in {"Arcade Mall", "South Metro", "Middle Cafe", "South East Hotel"}
    dur = (datetime.fromisoformat(b["end"]) - datetime.fromisoformat(b["start"])).total_seconds()
    assert dur == config.COOLDOWN_BREAK_MIN * 60


def test_no_break_with_high_threshold(synth_ctx, monkeypatch):
    monkeypatch.setattr(config, "RHL_BREAK_THRESHOLD", 1e9)
    stops = [_stop(synth_ctx, 0, "ne_corner"), _stop(synth_ctx, 1, "se_hotel")]
    res = planner.plan(
        synth_ctx, "walk", "tourist", _start(synth_ctx), stops, synth_ctx.at("summer", "13:00"), "summer"
    )
    assert res["breaks"] == []


def test_crew_policy_conflict_and_shift_window(synth_ctx):
    stops = [_stop(synth_ctx, 0, "shady_park", 30), _stop(synth_ctx, 1, "mid_cafe", 30)]
    t0 = synth_ctx.at("summer", "13:00")  # inside the 12:30-15:00 midday window in July
    res = planner.plan(synth_ctx, "walk", "crew", _start(synth_ctx), stops, t0, "summer")
    assert res["policy"] is not None and res["policy"]["verified"] is False
    assert res["policy"]["count"] >= 1 and any(i["kind"] == "work" for i in res["items"])
    shift = (synth_ctx.at("summer", "08:00"), synth_ctx.at("summer", "16:30"))
    best = planner.plan(synth_ctx, "walk", "crew", _start(synth_ctx), stops, t0, "summer", shift_window=shift)
    assert best["policy"]["count"] < res["policy"]["count"] or best["policy"]["count"] == 0
    assert "shift_search" in best


def test_permutation_scorer_matches_manual(synth_ctx):
    rt = planner._Router(synth_ctx, "walk", "summer")
    s = planner.Stop(-1, "s", 0, 0, 0, 0)
    a = _stop(synth_ctx, 0, "ne_corner", 0)
    c = planner._score_order(rt, s, [a], synth_ctx.at("summer", "13:00"), 0.25)
    r = rt.leg(0, a.node, synth_ctx.at("summer", "13:00"))
    assert c == pytest.approx(r.stats["rhl"] + 0.25 * r.stats["duration_s"])

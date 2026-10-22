"""Departure optimiser tests (synthetic fixture)."""
# ruff: noqa: F811

from __future__ import annotations

import time
from datetime import datetime, timedelta

import pytest

from tests.synth_fixtures import synth_ctx, synth_env  # noqa: F401
from zill.routing.departure import optimise_departure

ORIG, DEST = 6, 11  # row 1, west -> east ("Shady Lane" turns shaded at 14:00)


def _run(ctx, start="13:00", minutes=90, **kw):
    t0 = ctx.at("summer", start)
    end = t0 + timedelta(minutes=minutes)
    return optimise_departure(ctx, ORIG, DEST, "walk", t0, end, date_key="summer", **kw)


def test_table_shape_and_timing(synth_ctx):
    t = time.perf_counter()
    res = _run(synth_ctx)
    assert time.perf_counter() - t < 3.0
    assert len(res.table) == 19
    assert res.table[0]["wait_s"] == 0 and res.table[-1]["wait_s"] == 90 * 60
    assert {"depart", "duration_s", "sun_exposure_s", "shaded_pct", "rhl"} <= set(res.table[0])


def test_recommends_later_departure_and_explains(synth_ctx):
    res = _run(synth_ctx, mu=0.05)
    rec = res.recommended
    assert rec["wait_s"] > 0 and rec["rhl"] < res.requested["rhl"]
    assert rec["rhl_saved"] > 0 and rec["sun_saved_s"] > 0
    ch = res.why["changes"]
    assert ch and ch[0]["street"] == "Shady Lane" and ch[0]["direction"] == "into_shade"
    assert ch[0]["from_sun"] >= 0.9 and ch[0]["to_sun"] <= 0.5 and ch[0]["length_m"] > 0
    assert ch[0]["at"][:2] in ("13", "14")


def test_monotonic_in_mu(synth_ctx):
    """More penalty on waiting never makes the recommended wait longer; mu=0 minimises RHL."""
    waits = [_run(synth_ctx, mu=mu).recommended["wait_s"] for mu in (0.0, 0.05, 0.25, 1.0, 50.0)]
    assert waits == sorted(waits, reverse=True)
    assert waits[-1] == 0
    r0 = _run(synth_ctx, mu=0.0)
    assert r0.recommended["rhl"] == pytest.approx(min(x["rhl"] for x in r0.table))


def test_latest_arrival_constraint(synth_ctx):
    latest = synth_ctx.at("summer", "13:00") + timedelta(minutes=30)
    r = _run(synth_ctx, mu=0.0, latest_arrival=latest)
    assert datetime.fromisoformat(r.recommended["arrive"]) <= latest
    for x in r.table:
        assert x["feasible"] == (datetime.fromisoformat(x["arrive"]) <= latest)


def test_already_best_when_no_shade_change(synth_ctx):
    r = _run(synth_ctx, start="15:00", minutes=60)
    assert r.recommended["wait_s"] == 0 and r.why["changes"] == []

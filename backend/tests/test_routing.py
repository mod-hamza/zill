"""Routing invariants (PRD 18.1) on the synthetic fixture (+ real data if baked)."""
# ruff: noqa: F811

from __future__ import annotations

import os
import random

import pytest

from tests.synth_fixtures import synth_ctx, synth_env  # noqa: F401
from zill import config
from zill.routing import tdsp
from zill.routing.graph import NoRoute
from zill.routing.heat import rhl_edge, uv_factor

STUB = 30


def _nid(i, j):
    return j * 6 + i


def test_uv_factor_clip_and_shape():
    assert uv_factor(90.0) == pytest.approx(1.0)
    assert uv_factor(0.0) == pytest.approx(0.15)
    assert 0.15 < uv_factor(20.0) < 1.0
    assert uv_factor(-10.0) == pytest.approx(0.15)


def test_rhl_edge_formula():
    assert rhl_edge(10, 1.0, "open") == pytest.approx(10.0)
    assert rhl_edge(10, 0.0, "open") == pytest.approx(3.5)
    assert rhl_edge(10, 0.0, "covered") == pytest.approx(3.5)
    assert rhl_edge(10, 0.0, "ac_link") == pytest.approx(1.0)
    assert rhl_edge(10, 0.5, "indoor") == pytest.approx(1.0)


def test_basic_route_and_stats(synth_ctx):
    dep = synth_ctx.at("summer", "13:00")
    r = tdsp.route(synth_ctx, 0, 5, "walk", dep, 0.0, "summer")
    assert r.nodes == [0, 1, 2, 3, 4, 5]
    assert r.stats["distance_m"] == pytest.approx(500.0)
    assert r.stats["duration_s"] == pytest.approx(500 / 1.4, abs=0.02)
    assert r.stats["sun_exposure_s"] == pytest.approx(r.stats["duration_s"], abs=0.02)
    assert len(r.segments) == 5 and r.segments[0]["cls"] == "open"
    assert r.segments[0]["latlon"] and r.segments[0]["geometry"][0] == [-250.0, -200.0]
    assert [s["arrival_s"] for s in r.segments] == sorted(s["arrival_s"] for s in r.segments)
    d = r.to_dict()
    assert d["lambda"] == 0.0 and d["label"] == "fastest" and d["depart"].endswith("+04:00")


def test_lookup_uses_arrival_time_not_departure_time(synth_ctx):
    """Row 1 turns shaded 14:00-14:10. Depart 13:59: later edges must see the shade that arrives."""
    dep = synth_ctx.at("summer", "13:59")
    r = tdsp.route(synth_ctx, _nid(0, 1), _nid(5, 1), "walk", dep, 3.0, "summer", with_geometry=True)
    assert r.edges and all(synth_ctx.graph.name[e] == "Shady Lane" for e in r.edges)
    tab = synth_ctx.exposure("summer")
    m0 = tab.minute_of(dep)
    for seg in r.segments:
        assert seg["sun"] == pytest.approx(tab.sun(seg["edge"], m0 + seg["arrival_s"] / 60.0), abs=1e-3)
    # sunny when evaluated at departure, but shaded by the time the traveller gets there
    assert r.segments[0]["sun"] > 0.9 and r.segments[-1]["sun"] < r.segments[0]["sun"] - 0.3
    naive = sum(seg["t_s"] * tab.sun(seg["edge"], m0) for seg in r.segments)
    assert r.stats["sun_exposure_s"] < naive - 5


def test_time_dependence_changes_route_choice(synth_ctx):
    early = tdsp.compare(synth_ctx, 0, 5, "walk", synth_ctx.at("summer", "13:00"), "summer")
    late = tdsp.compare(synth_ctx, 0, 5, "walk", synth_ctx.at("summer", "14:30"), "summer")
    assert early["coolest"].nodes == [0, 1, 2, 3, 4, 5] and early["coolest"].stats["sun_saved_s"] == 0
    assert late["coolest"].nodes != late["fastest"].nodes
    assert late["coolest"].stats["sun_saved_s"] > 100 and late["coolest"].stats["added_time_s"] > 0
    assert late["coolest"].stats["rhl_saved_pct"] > 10
    names = {synth_ctx.graph.name[e] for e in late["coolest"].edges}
    assert "Shady Lane" in names


def test_stairs_walk_only_and_slow(synth_ctx):
    dep = synth_ctx.at("summer", "13:00")
    r = tdsp.route(synth_ctx, _nid(5, 4), STUB, "walk", dep, 0.0, "summer")
    assert r.stats["duration_s"] == pytest.approx(50.0 / (1.4 * config.STAIRS_WALK_FACTOR), abs=0.05)
    for mode in ("cycle", "scooter"):
        with pytest.raises(NoRoute):
            tdsp.route(synth_ctx, _nid(5, 4), STUB, mode, dep, 0.0, "summer")


def test_crossing_wait_and_ac_crowd(synth_ctx):
    dep = synth_ctx.at("summer", "13:00")
    # row 1 passes crossing node (3,1)
    w = tdsp.route(synth_ctx, _nid(0, 1), _nid(5, 1), "walk", dep, 0.0, "summer")
    assert w.stats["duration_s"] == pytest.approx(500 / 1.4 + 8.0, abs=0.05)
    c = tdsp.route(synth_ctx, _nid(0, 1), _nid(5, 1), "cycle", dep, 0.0, "summer")
    assert c.stats["duration_s"] == pytest.approx(500 / 4.5 + 10.0, abs=0.05)
    # a crossing node as ORIGIN adds no wait
    o = tdsp.route(synth_ctx, _nid(3, 1), _nid(5, 1), "walk", dep, 0.0, "summer")
    assert o.stats["duration_s"] == pytest.approx(200 / 1.4, abs=0.05)
    # ac_link corridor (1,4)->(4,4): sun-free, 15% slower
    a = tdsp.route(synth_ctx, _nid(1, 4), _nid(4, 4), "walk", dep, 0.0, "summer")
    assert a.stats["duration_s"] == pytest.approx(300 / 1.4 * 1.15, abs=0.05)
    assert a.stats["sun_exposure_s"] == 0 and a.stats["indoor_pct"] == pytest.approx(100.0)
    assert a.stats["rhl"] == pytest.approx(a.stats["duration_s"] * 0.1, abs=0.05)


def test_covered_edge_is_sun_free(synth_ctx):
    dep = synth_ctx.at("summer", "13:00")
    r = tdsp.route(synth_ctx, _nid(2, 3), _nid(3, 3), "walk", dep, 0.0, "summer")
    assert r.segments[0]["cls"] == "covered" and r.segments[0]["sun"] == 0
    assert r.stats["covered_pct"] == pytest.approx(100.0)


def test_cycle_never_uses_stairs_or_foot_only(synth_ctx):
    g = synth_ctx.graph
    dep = synth_ctx.at("summer", "13:00")
    rng = random.Random(7)
    for _ in range(40):
        a, b = rng.sample(range(30), 2)
        for mode in ("cycle", "scooter"):
            res = tdsp.compare(synth_ctx, a, b, mode, dep, "summer", with_geometry=False)
            for r in res.values():
                assert not tdsp.uses_disallowed_edge(synth_ctx, r)
                assert not any(g.stairs[e] for e in r.edges)
                assert all(g.allowed[mode][e] for e in r.edges)


def _check_invariants(ctx, a, b, mode, dep, date_key):
    res = tdsp.compare(ctx, a, b, mode, dep, date_key, with_geometry=False)
    f, bal, c = res["fastest"].stats, res["balanced"].stats, res["coolest"].stats
    eps = 0.011
    assert f["duration_s"] <= bal["duration_s"] + eps and f["duration_s"] <= c["duration_s"] + eps, "fastest"
    assert c["rhl"] <= f["rhl"] + eps and c["rhl"] <= bal["rhl"] + eps, "coolest min RHL"
    assert c["sun_exposure_s"] <= f["sun_exposure_s"] + eps, "coolest sun <= fastest"
    assert f["added_time_s"] == 0
    assert c["sun_saved_s"] >= -eps
    for r in res.values():
        assert not tdsp.uses_disallowed_edge(ctx, r)


@pytest.mark.parametrize("mode", ["walk", "cycle"])
def test_invariants_random_pairs_synth(synth_ctx, mode):
    rng = random.Random(11)
    for _ in range(30):
        a, b = rng.sample(range(30), 2)
        hh = rng.choice(["09:00", "12:30", "13:50", "14:00", "15:30", "17:45"])
        _check_invariants(synth_ctx, a, b, mode, synth_ctx.at("summer", hh), "summer")


def test_astar_matches_dijkstra_cost(synth_ctx):
    """A* with the straight-line heuristic must equal the h~0 (Dijkstra) optimum cost."""
    g = synth_ctx.graph
    mg = g.mode_graph("walk")
    tab = synth_ctx.exposure("summer")
    dmin = tab.minute_of(synth_ctx.at("summer", "13:45"))

    def cost(nodes, edges):
        _, segs, _ = tdsp.evaluate_path(g, mg, tab, nodes, edges, dmin, True, synth_ctx.origin)
        tot = 0.0
        for s in segs:
            uv = tab.uv_at(dmin + s["arrival_s"] / 60.0)
            sun = s["sun"] if s["cls"] == "open" else 0
            tot += s["t_s"] + s["t_s"] * 3.0 * uv * mg.pen_w[s["edge"]] * sun
        return tot

    rng = random.Random(3)
    for _ in range(25):
        a, b = rng.sample(range(30), 2)
        p1 = tdsp._search(g, mg, tab, a, b, dmin, 3.0, config.SPEEDS["walk"])
        p2 = tdsp._search(g, mg, tab, a, b, dmin, 3.0, 1e12)
        assert cost(*p1) == pytest.approx(cost(*p2), rel=1e-3)


def test_o_equals_d(synth_ctx):
    r = tdsp.route(synth_ctx, 5, 5, "walk", synth_ctx.at("summer", "12:00"), 1.0, "summer")
    assert r.nodes == [5] and r.stats["duration_s"] == 0 and r.segments == []


def test_coolest_never_worse_than_fastest(synth_ctx):
    r = tdsp.compare(synth_ctx, 0, 5, "walk", synth_ctx.at("summer", "13:00"), "summer")
    assert r["coolest"].stats["rhl"] <= r["fastest"].stats["rhl"] + 1e-6


# ---- real data (skipped if not baked) ------------------------------------------------------------
def _real_ctx():
    if os.environ.get("ZILL_CITIES_DIR"):
        return None
    try:
        from zill.services import get_city

        ctx = get_city(config.DEFAULT_CITY)
        ctx.exposure("summer")
        return ctx
    except Exception:
        return None


def test_invariants_real_data():
    ctx = _real_ctx()
    if ctx is None:
        pytest.skip("real city + exposure not baked yet")
    rng = random.Random(5)
    for mode, n in (("walk", 30), ("cycle", 10)):
        ids = [int(i) for i in ctx.graph.mode_graph(mode).node_ids]
        for _ in range(n):
            a, b = rng.sample(ids, 2)
            hh = rng.choice(["12:30", "13:30", "14:30", "15:30"])
            try:
                _check_invariants(ctx, a, b, mode, ctx.at("summer", hh), "summer")
            except NoRoute:
                continue

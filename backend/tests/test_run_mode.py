"""Run mode: the walk graph at running pace (config.SPEEDS['run']), through engine and API."""
# ruff: noqa: F811

from __future__ import annotations

from typing import get_args

import pytest

from tests.synth_fixtures import client, synth_ctx, synth_env  # noqa: F401
from zill import config
from zill.api.schemas import DepartureRequest, PlanRequest, RouteRequest
from zill.routing import modes, tdsp
from zill.routing.case_studies import loop_routes


@pytest.fixture(autouse=True)
def _no_live(monkeypatch):
    monkeypatch.setenv("ZILL_WEATHER_LIVE", "0")
    monkeypatch.setenv("ZILL_NOMINATIM", "0")


def test_run_constants():
    assert "run" in modes.MODES
    assert config.SPEEDS["run"] == pytest.approx(2.8)
    # about 6:00 min/km
    assert 1000 / config.SPEEDS["run"] / 60 == pytest.approx(5.95, abs=0.05)
    assert config.CROSSING_WAIT_S["run"] == config.CROSSING_WAIT_S["walk"]
    assert config.SUN_WEIGHT["run"] == config.SUN_WEIGHT["walk"]


def test_run_uses_walk_graph(synth_ctx):
    g = synth_ctx.graph
    assert (g.allowed["run"] == g.allowed["walk"]).all()
    assert list(g.mode_graph("run").node_ids) == list(g.mode_graph("walk").node_ids)


def test_run_same_path_twice_as_fast_as_walk(synth_ctx):
    dep = synth_ctx.at("summer", "13:00")
    w = tdsp.route(synth_ctx, 0, 5, "walk", dep, 0.0, "summer")
    r = tdsp.route(synth_ctx, 0, 5, "run", dep, 0.0, "summer")
    assert r.nodes == w.nodes == [0, 1, 2, 3, 4, 5]
    assert r.stats["distance_m"] == pytest.approx(w.stats["distance_m"])
    assert r.stats["duration_s"] == pytest.approx(500 / 2.8, abs=0.02)
    assert r.mode == "run"


def test_run_compare_shade_and_sun(synth_ctx):
    dep = synth_ctx.at("summer", "14:30")
    sh = tdsp.compare(synth_ctx, 0, 5, "run", dep, "summer")
    assert sh["coolest"].stats["sun_exposure_s"] <= sh["fastest"].stats["sun_exposure_s"] + 1e-6
    su = tdsp.compare(synth_ctx, 0, 5, "run", dep, "summer", preference="sun")
    assert su["sunniest"].stats["sun_exposure_s"] >= su["fastest"].stats["sun_exposure_s"] - 1e-6


def test_run_loop_return_departs_at_arrival(synth_ctx):
    dep = synth_ctx.at("summer", "14:30")
    lr = loop_routes(synth_ctx, 0, 5, "run", dep, "summer", "shade")
    for out, back in lr.values():
        assert back.depart.timestamp() == pytest.approx(dep.timestamp() + out.stats["duration_s"], abs=1e-3)
        assert back.nodes[0] == out.nodes[-1] and back.nodes[-1] == out.nodes[0]


def test_schemas_accept_run():
    assert "run" in get_args(RouteRequest.model_fields["mode"].annotation)
    assert DepartureRequest.model_fields["mode"].annotation == RouteRequest.model_fields["mode"].annotation
    assert PlanRequest.model_fields["mode"].annotation == RouteRequest.model_fields["mode"].annotation


def test_api_route_run(client):
    body = {
        "city": "synth",
        "mode": "run",
        "origin": {"poi": "nw_corner"},
        "dest": {"poi": "ne_corner"},
        "depart_at": "2026-07-15T14:30:00+04:00",
    }
    r = client.post("/api/route", json=body)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["fastest"]["mode"] == "run"
    w = client.post("/api/route", json={**body, "mode": "walk"}).json()
    assert j["fastest"]["stats"]["duration_s"] < w["fastest"]["stats"]["duration_s"]

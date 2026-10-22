"""Contract tests for routing / departure / plan / weather / gazetteer / scenarios / health endpoints."""
# ruff: noqa: F811

from __future__ import annotations

import json

import pytest

from tests.synth_fixtures import client, synth_env  # noqa: F401

ROUTE_KEYS = {"lambda", "label", "mode", "depart", "stats", "nodes", "edges", "segments"}
STAT_KEYS = {
    "distance_m",
    "duration_s",
    "sun_exposure_s",
    "shaded_pct",
    "covered_pct",
    "indoor_pct",
    "rhl",
    "added_time_s",
    "sun_saved_s",
    "sun_saved_pct",
    "rhl_saved_pct",
}


@pytest.fixture(autouse=True)
def _no_live(monkeypatch):
    monkeypatch.setenv("ZILL_WEATHER_LIVE", "0")
    monkeypatch.setenv("ZILL_NOMINATIM", "0")


def _route_body(**kw):
    b = {
        "city": "synth",
        "mode": "walk",
        "origin": {"poi": "nw_corner"},
        "dest": {"poi": "ne_corner"},
        "depart_at": "2026-07-15T14:30:00+04:00",
    }
    b.update(kw)
    return b


def test_route_contract(client):
    r = client.post("/api/route", json=_route_body())
    assert r.status_code == 200, r.text
    j = r.json()
    assert set(j) >= {"fastest", "balanced", "coolest", "origin", "dest", "date_key"}
    assert j["date_key"] == "summer"  # ISO date of a preset maps to the preset
    for label in ("fastest", "balanced", "coolest"):
        rt = j[label]
        assert ROUTE_KEYS <= set(rt) and rt["label"] == label
        assert STAT_KEYS <= set(rt["stats"])
        seg = rt["segments"][0]
        assert {"edge", "geometry", "latlon", "arrival_s", "t_s", "sun", "cls"} <= set(seg)
        assert rt["depart"].endswith("+04:00")
    assert j["fastest"]["stats"]["added_time_s"] == 0
    assert j["coolest"]["stats"]["sun_saved_s"] > 100
    assert j["fastest"]["lambda"] == 0 and j["coolest"]["lambda"] == 3.0
    assert j["origin"]["node"] == 0 and j["dest"]["node"] == 5
    assert j["fastest"]["stats"]["duration_s"] <= j["coolest"]["stats"]["duration_s"]


def test_route_hhmm_date_key_lambdas_and_latlon_places(client):
    ctx_pt = client.get("/api/cities/synth/files/pois.json").json()["pois"][0]
    r = client.post(
        "/api/route",
        json=_route_body(
            origin={"lat": ctx_pt["lat"], "lon": ctx_pt["lon"], "name": "Start"},
            dest="ne_corner",
            depart_at="13:00",
            date_key="summer",
            lambdas=[0, 2, 5],
            include_segments=False,
        ),
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["origin"]["name"] == "Start" and j["fastest"]["segments"] == []
    assert j["balanced"]["lambda"] == 2.0 and j["coolest"]["lambda"] == 5.0


def test_route_cycle_and_errors(client):
    r = client.post("/api/route", json=_route_body(mode="cycle"))
    assert r.status_code == 200
    j = r.json()
    g = client.get("/api/cities/synth/files/graph.json").json()["edges"]
    for label in ("fastest", "balanced", "coolest"):
        assert all(g["cycle"][e] and not g["stairs"][e] for e in j[label]["edges"])
    bad = client.post("/api/route", json=_route_body(dest={"lat": 10.0, "lon": 10.0}))
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "place_error"
    assert "Traceback" not in bad.text
    assert client.post("/api/route", json=_route_body(city="atlantis")).status_code == 404
    assert client.post("/api/route", json=_route_body(mode="hoverboard")).status_code == 422
    assert client.post("/api/route", json=_route_body(depart_at="soon")).status_code == 422
    assert client.post("/api/route", json=_route_body(lambdas=[1, 2])).status_code == 422
    # stub node 30 is reachable only via stairs: cycle -> typed no_route
    nr = client.post("/api/route", json=_route_body(mode="cycle", dest={"node": 30}))
    assert nr.status_code in (404, 422) and "error" in nr.json()
    unc = client.post("/api/route", json=_route_body(depart_at="2026-03-03T14:00:00+04:00"))
    assert unc.status_code == 409 and unc.json()["error"]["code"] == "shade_unavailable"


def test_request_id_header(client):
    r = client.get("/api/cities", headers={"X-Request-ID": "abc123"})
    assert r.headers["x-request-id"] == "abc123"
    assert client.get("/api/cities").headers["x-request-id"]


def test_departure_contract(client):
    body = {
        "city": "synth",
        "mode": "walk",
        "origin": {"node": 6},
        "dest": {"node": 11},
        "depart_at": "2026-07-15T13:00:00+04:00",
        "mu": 0.05,
    }
    r = client.post("/api/departure", json=body)
    assert r.status_code == 200, r.text
    j = r.json()
    assert len(j["table"]) == 19
    assert {"depart", "duration_s", "sun_exposure_s", "shaded_pct", "rhl"} <= set(j["table"][0])
    assert j["recommended"]["wait_s"] > 0 and j["recommended"]["rhl"] < j["requested"]["rhl"]
    assert j["why"]["changes"][0]["street"] == "Shady Lane"
    assert j["timing_ms"] < 3000
    w = client.post(
        "/api/departure", json={**body, "window": {"start": "13:00", "end": "13:30"}, "step_min": 10}
    )
    assert w.status_code == 200 and len(w.json()["table"]) == 4
    assert (
        client.post("/api/departure", json={**body, "window": {"start": "14:00", "end": "13:00"}}).status_code
        == 422
    )


def test_plan_contract(client):
    body = {
        "city": "synth",
        "mode": "walk",
        "persona": "tourist",
        "start": {"poi": "south_metro"},
        "stops": [
            {"place": {"poi": "ne_corner"}, "dwell_min": 20},
            {"place": {"poi": "mid_cafe"}, "dwell_min": 30},
            {"place": {"poi": "arcade_mall"}, "dwell_min": 15},
        ],
        "start_at": "2026-07-15T13:00:00+04:00",
    }
    r = client.post("/api/plan", json=body)
    assert r.status_code == 200, r.text
    j = r.json()
    assert sorted(j["order"]) == [0, 1, 2] and j["plan_id"].startswith("plan_")
    assert len(j["legs"]) >= 3 and j["totals"]["duration_s"] > 0
    assert client.post("/api/plan", json={**body, "stops": []}).status_code == 422


def test_weather_representative(client):
    r = client.get(
        "/api/weather", params={"city": "synth", "at": "2026-07-15T14:00:00+04:00", "hourly": "true"}
    )
    assert r.status_code == 200
    j = r.json()
    assert j["source"] == "representative" and "not a measurement" in j["label"]
    assert j["heat_alert"] is True and len(j["hourly"]) == 24
    assert j["uv_basis"] == "clear_sky_estimate"
    assert client.get("/api/weather", params={"city": "synth", "at": "x"}).status_code == 422


def test_gazetteer(client):
    j = client.get("/api/gazetteer/synth", params={"q": "metro"}).json()
    assert j["results"][0]["id"] == "south_metro" and j["online_fallback"] is False
    j = client.get("/api/gazetteer/synth", params={"q": "arcad mal"}).json()
    assert j["results"][0]["id"] == "arcade_mall"
    assert client.get("/api/gazetteer/synth", params={"q": "zzzzqq"}).json()["results"] == []
    assert client.get("/api/gazetteer/nowhere", params={"q": "x"}).status_code == 404


def test_scenarios_endpoint(client, tmp_path, monkeypatch):
    monkeypatch.setenv("ZILL_SCENARIOS_DIR", str(tmp_path))
    assert client.get("/api/scenarios/synth").status_code == 404
    (tmp_path / "hero_synth.json").write_text(json.dumps({"scenarios": [{"id": "tourist_walk"}]}))
    assert client.get("/api/scenarios/synth").json()["scenarios"][0]["id"] == "tourist_walk"


def test_health_extended(client):
    j = client.get("/api/health").json()
    assert j["ok"] is True and j["service"] == "zill"
    assert {"city", "shade", "replay_available", "llm"} <= set(j)
    assert {"base_url", "model", "key_present"} <= set(j["llm"])


def test_shade_compute_validation(client):
    assert (
        client.post("/api/shade/compute", json={"city": "atlantis", "date": "2026-03-03"}).status_code == 404
    )
    assert client.post("/api/shade/compute", json={"city": "synth", "date": "../x"}).status_code == 422


def test_openapi_lists_every_endpoint(client):
    paths = set(client.get("/openapi.json").json()["paths"])
    want = {
        "/api/health",
        "/api/cities",
        "/api/cities/{city_id}/meta",
        "/api/cities/{city_id}/files/{path}",
        "/api/cities/build",
        "/api/sun",
        "/api/shade/{city_id}/{date_id}/{hhmm}.png",
        "/api/shade/compute",
        "/api/route",
        "/api/departure",
        "/api/plan",
        "/api/weather",
        "/api/gazetteer/{city}",
        "/api/scenarios/{city}",
    }
    assert want <= paths, want - paths

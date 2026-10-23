"""Assertions on the Central Oslo bake (Stream D). Skipped if the bake is absent."""

from __future__ import annotations

import json
import math
from datetime import date

import numpy as np
import pytest

from zill import config
from zill.sun.position import sun_position, sun_times

CITY = config.CITIES_DIR / "oslo"
pytestmark = pytest.mark.skipif(
    not (CITY / "meta.json").exists(), reason="Oslo bake absent: run python -m zill.data.bake --city oslo"
)
DATES = {"winter": "2026-12-21", "spring": "2026-03-20", "summer": "2026-06-21", "hackathon": "2026-10-24"}


def _load(name: str):
    return json.loads((CITY / name).read_text(encoding="utf-8"))


def test_meta_city_and_dates():
    m = _load("meta.json")
    assert m["timezone"] == "Europe/Oslo"
    assert m["dates"] == DATES
    assert m["caster_buffer_m"] == 1500
    assert m["attribution"] == "© OpenStreetMap contributors"


def test_counts_sane():
    c = _load("meta.json")["counts"]
    # guards against pipeline regressions; real numbers are reported in docs/PROGRESS.md
    assert c["buildings_scene"] > 1_500
    assert c["edges_walk"] > 5_000
    assert c["trees"] > 1_000
    assert c["pois"] >= 13


def test_landmark_pois_resolved_from_osm():
    pois = {p["id"]: p for p in _load("pois.json")["pois"]}
    for pid in ("oslo_s", "oslo_opera_house", "akershus_fortress", "oslo_city_hall", "aker_brygge"):
        assert pois[pid]["source"] == "osm", pid
        assert isinstance(pois[pid]["node"], int)


def test_glb_size_discipline():
    assert (CITY / "buildings.glb").stat().st_size < 8_000_000


def test_caster_ring_covers_tallest_building_at_midwinter_noon():
    m = _load("meta.json")
    lat, lon, tz = m["origin"]["lat"], m["origin"]["lon"], m["timezone"]
    st = sun_times(date.fromisoformat(m["dates"]["winter"]), lat, lon, tz)
    alt = sun_position(st["solar_noon"], lat, lon, tz).alt_deg
    # a building of max height in the ring casts at most h/tan(alt) at noon; the ring is wider than that
    assert m["max_building_height_m"] / math.tan(math.radians(alt)) <= m["caster_buffer_m"]


@pytest.mark.skipif(not (CITY / "exposure_winter.npz").exists(), reason="Oslo shade bake absent")
def test_winter_steps_flag_night_and_day_has_long_shadows():
    idx = json.loads((CITY / "shade" / "winter" / "index.json").read_text(encoding="utf-8"))
    steps = idx["steps"]
    assert idx["date"] == "2026-12-21"
    assert steps[0]["night"] and steps[-1]["night"]
    day = [s for s in steps if not s["night"]]
    assert day and max(s["alt"] for s in day) < 7.0
    with np.load(CITY / "exposure_winter.npz") as z:
        night = z["night"]
        expo = z["exposure"].astype(np.float32)
    assert night.tolist() == [s["night"] for s in steps]
    assert float(expo[:, night].max()) == 0.0  # no sun at night ...
    # ... and at midwinter noon most open street length is in building shadow (low sun, long shadows)
    noon = int(np.argmax([s["alt"] for s in steps]))
    summer = np.load(CITY / "exposure_summer.npz")["exposure"].astype(np.float32)
    s_noon = int(np.argmax([s["alt"] for s in json.loads(
        (CITY / "shade" / "summer" / "index.json").read_text(encoding="utf-8"))["steps"]]))
    assert float(expo[:, noon].mean()) < float(summer[:, s_noon].mean())


@pytest.mark.skipif(not (CITY / "exposure_summer.npz").exists(), reason="Oslo shade bake absent")
def test_api_lists_oslo_ready_and_routes():
    from fastapi.testclient import TestClient

    from zill.api.main import app

    c = TestClient(app)
    cities = {x["id"]: x for x in c.get("/api/cities").json()}
    assert cities["oslo"]["status"] == "ready"
    assert set(cities["oslo"]["shade_dates"]) == set(DATES)
    assert "dubai_downtown" in cities
    body = {"city": "oslo", "mode": "walk", "origin": {"poi": "oslo_s"}, "dest": {"poi": "oslo_city_hall"},
            "depart_at": "2026-06-21T13:00:00+02:00"}
    r = c.post("/api/route", json=body)
    assert r.status_code == 200, r.text
    j = r.json()
    f = j["fastest"]["stats"]
    assert 1_000 < f["distance_m"] < 3_000  # Oslo S -> City Hall is ~1.4 km as the crow flies
    assert j["coolest"]["stats"]["sun_exposure_s"] <= f["sun_exposure_s"] + 1e-6
    # sun mode (Stream A) if available
    r2 = c.post("/api/route", json={**body, "preference": "sun"})
    if r2.status_code == 200 and r2.json().get("preference") == "sun":
        j2 = r2.json()
        assert j2["best"]["stats"]["sun_exposure_s"] >= j2["fastest"]["stats"]["sun_exposure_s"] - 1e-6

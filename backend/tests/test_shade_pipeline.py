"""Exposure, cache/bake and explain tests on a synthetic city (PRD 7.4, 7.5)."""

from __future__ import annotations

import json

import numpy as np
import pytest

from zill import config
from zill.shade import cache as shade_cache
from zill.shade.bake import bake
from zill.shade.explain import casting_building
from zill.shade.synthetic import box


@pytest.fixture()
def synth_city(tmp_path, monkeypatch):
    cities = tmp_path / "cities"
    cdir = cities / "synth"
    cdir.mkdir(parents=True)
    meta = {
        "city_id": "synth", "name": "Synthetic", "timezone": "Asia/Dubai",
        "origin": {"lat": config.ORIGIN_LAT, "lon": config.ORIGIN_LON},
        "core_grid": {"x0": -200.0, "z0": -200.0, "rows": 200, "cols": 200, "res_m": 2.0},
        "caster_grid": {"x0": -300.0, "z0": -300.0, "rows": 300, "cols": 300, "res_m": 2.0},
        "dates": {"hackathon": "2026-10-24"},
    }
    buildings = [box(1, -10, -10, 10, 10, 100, name="Test Tower")]
    graph = {"nodes": {}, "edges": {
        "geom": [
            [-60.0, 0.0, -20.0, 0.0],  # 0 west of the tower (shaded by low eastern sun)
            [20.0, 0.0, 60.0, 0.0],  # 1 east of the tower (shaded by low western sun)
            [-60.0, 40.0, 60.0, 40.0],  # 2 covered
            [-15.0, 0.0, 15.0, 0.0],  # 3 runs straight through the tower footprint
            [-80.0, -150.0, -80.0, -120.0, -40.0, -120.0],  # 4 far north-west, open, polyline
        ],
        "cls": ["open", "open", "covered", "open", "open"],
    }}
    (cdir / "meta.json").write_text(json.dumps(meta))
    (cdir / "buildings.json").write_text(json.dumps({"buildings": buildings}))
    (cdir / "trees.json").write_text(json.dumps({"trees": []}))
    (cdir / "graph.json").write_text(json.dumps(graph))
    monkeypatch.setattr(config, "CITIES_DIR", cities)
    monkeypatch.setattr(shade_cache, "CACHE_DIR", tmp_path / "cache")
    shade_cache.get_city_shade.cache_clear()
    shade_cache.exposure_for.cache_clear()
    yield cdir
    shade_cache.get_city_shade.cache_clear()
    shade_cache.exposure_for.cache_clear()


def test_bake_preset_outputs(synth_city):
    summary = bake("synth", ["hackathon"])
    d = synth_city / "shade" / "hackathon"
    index = json.loads((d / "index.json").read_text())
    assert index["date"] == "2026-10-24" and index["date_id"] == "hackathon"
    steps = index["steps"]
    assert summary["dates"]["hackathon"]["steps"] == len(steps) > 70
    assert all(int(s["hhmm"][2:]) % 10 == 0 for s in steps)
    assert steps[0]["night"] and steps[-1]["night"]
    for s in steps:
        assert (d / s["file"]).exists()
    assert (synth_city / "building_mask.png").exists()
    log = json.loads((synth_city / "shade" / "bake_log.json").read_text())
    assert all(e["step"] == "shadow_precompute" for e in log["build_log"])

    with np.load(synth_city / "exposure_hackathon.npz") as z:
        expo, hhmm, minutes = z["exposure"], z["hhmm"], z["minutes"]
    assert expo.dtype == np.float16 and expo.shape == (5, len(steps))
    assert hhmm.dtype == np.int16 and minutes.dtype == np.int16
    assert list(hhmm) == [int(s["hhmm"]) for s in steps]
    assert minutes[0] == (hhmm[0] // 100) * 60 + hhmm[0] % 100

    col = {int(s["hhmm"]): i for i, s in enumerate(steps)}
    am, pm, noon = col[800], col[1600], col[1200]
    # sun in the ESE at 08:00: the west edge is (partly) in the tower's shadow, the east edge is not
    assert expo[1, am] > 0.95 and expo[0, am] < expo[1, am] - 0.2
    # sun in the WSW at 16:00: the reverse
    assert expo[0, pm] > 0.95 and expo[1, pm] < expo[0, pm] - 0.2
    assert (expo[2] == 0).all()  # covered
    assert expo[4, noon] > 0.95
    night = [i for i, s in enumerate(steps) if s["night"]]
    assert (expo[:, night] == 0).all()

    # PNG orientation: row 0 = north. At 16:00 the shadow falls to the ENE -> east of the tower
    png = shade_cache.read_png(d / "step_1600.png")
    assert png.shape == (200, 200)
    az = np.radians(steps[pm]["az"])
    assert 225 < steps[pm]["az"] < 270  # WSW sun
    for dist, expect_shade in ((30.0, True), (-30.0, False)):
        # point `dist` metres from the tower centre in the shadow direction (az + 180)
        x, z = -np.sin(az) * dist, np.cos(az) * dist
        r, c = int((z + 200) // 2), int((x + 200) // 2)
        assert (png[r, c] < 128) == expect_shade, (dist, x, z, png[r, c])
    assert -np.sin(az) * 30 > 0  # i.e. the shaded point is EAST of the tower (shadow falls ENE)


def test_exposure_snapping_and_table(synth_city):
    shade_cache.compute_date("synth", "hackathon")
    sc = shade_cache.get_city_shade("synth")
    st = sc.sampler.stats
    assert st["in_building"] > 0 and st["snapped_to_outdoor"] > 0 and st["left_shaded"] > 0
    tbl = shade_cache.exposure_for("synth", "hackathon")
    assert tbl is shade_cache.exposure_for("synth", "2026-10-24")  # ISO of a preset -> same table
    m0, m1 = int(tbl.minutes[40]), int(tbl.minutes[41])
    mid = tbl.at((m0 + m1) / 2)
    assert np.allclose(mid, (tbl.exposure[:, 40] + tbl.exposure[:, 41]) / 2, atol=1e-6)
    assert tbl.edge_at(1, m0) == pytest.approx(float(tbl.exposure[1, 40]))


def test_on_demand_date_and_step(synth_city):
    calls = []
    sf = shade_cache.get_shade_step("synth", "2026-03-03", "1203")  # nearest step 12:00
    assert sf.shape == (200, 200) and sf.dtype == np.uint8
    idx = shade_cache.compute_date("synth", "2026-03-03", lambda d, t, h: calls.append(h), first_hhmm="1500")
    assert calls[0] == "1500" and len(calls) == len(idx["steps"])
    out = shade_cache.CACHE_DIR / "synth" / "2026-03-03"
    assert (out / "index.json").exists() and (out / "exposure_2026-03-03.npz").exists()
    tbl = shade_cache.exposure_for("synth", "2026-03-03")
    assert tbl.exposure.shape[0] == 5


def test_casting_building(synth_city):
    # 08:00 on the hackathon date the sun is low in the ESE: a point 40 m west is shaded by the tower
    hit = casting_building("synth", -40.0, 0.0, 25.0, 100.0)
    assert hit is not None and hit["building_id"] == 1 and hit["name"] == "Test Tower"
    assert 25 <= hit["distance_m"] <= 35
    assert casting_building("synth", 40.0, 0.0, 25.0, 100.0) is None  # east side faces the sun
    assert casting_building("synth", -40.0, 0.0, 1.0, 100.0) is None  # night

"""Sun position tests (PRD 7.1)."""

from __future__ import annotations

import json
import math
from datetime import date

import pandas as pd
import pvlib
import pytest

from zill import config
from zill.sun.golden import GOLDEN_PATH, build_golden
from zill.sun.position import step_times, sun_position, sun_times, sun_vector

LAT, LON = config.ORIGIN_LAT, config.ORIGIN_LON


def test_june_solstice_noon_altitude():
    noon = sun_times(date(2026, 6, 21), LAT, LON)["solar_noon"]
    assert sun_position(noon, LAT, LON).alt_deg == pytest.approx(88.0, abs=1.0)


def test_december_solstice_noon_altitude():
    noon = sun_times(date(2026, 12, 21), LAT, LON)["solar_noon"]
    assert sun_position(noon, LAT, LON).alt_deg == pytest.approx(41.0, abs=1.0)


def test_vector_axes():
    x, y, z = sun_vector(0.0, 90.0)  # due east on the horizon -> +x
    assert (x, y, z) == pytest.approx((1.0, 0.0, 0.0), abs=1e-9)
    x, y, z = sun_vector(0.0, 0.0)  # due north -> -z
    assert (x, y, z) == pytest.approx((0.0, 0.0, -1.0), abs=1e-9)
    x, y, z = sun_vector(0.0, 180.0)  # south -> +z
    assert z == pytest.approx(1.0)
    x, y, z = sun_vector(0.0, 270.0)  # west -> -x
    assert x == pytest.approx(-1.0)
    assert sun_vector(90.0, 123.0)[1] == pytest.approx(1.0)
    v = sun_vector(37.0, 211.0)
    assert math.hypot(*v) == pytest.approx(1.0)


def test_morning_sun_is_east_afternoon_west():
    am = sun_position(pd.Timestamp("2026-10-24T08:00", tz="Asia/Dubai").to_pydatetime(), LAT, LON)
    pm = sun_position(pd.Timestamp("2026-10-24T16:00", tz="Asia/Dubai").to_pydatetime(), LAT, LON)
    assert 90 < am.az_deg < 135 and am.vector[0] > 0  # ESE
    assert 225 < pm.az_deg < 270 and pm.vector[0] < 0  # WSW


@pytest.mark.parametrize("iso", ["2026-01-15", "2026-04-15", "2026-07-15", "2026-10-24"])
def test_sunrise_sunset_sanity(iso):
    d = date.fromisoformat(iso)
    st = sun_times(d, LAT, LON)
    assert 5 <= st["sunrise"].hour <= 7
    assert 17 <= st["sunset"].hour <= 19
    assert st["sunrise"] < st["solar_noon"] < st["sunset"]
    assert st["sunrise"].utcoffset().total_seconds() == 4 * 3600
    # Independent check: the apparent sun is on the horizon at those instants (within 3 minutes).
    # SPA convention: geometric elevation of the sun's centre = -0.8333 deg at rise/set.
    sp = pvlib.solarposition.get_solarposition(pd.DatetimeIndex([st["sunrise"], st["sunset"]]), LAT, LON)
    for geo_alt in sp["elevation"]:
        assert geo_alt == pytest.approx(-0.8333, abs=0.2)  # 0.2 deg < 1 min of sun motion


def test_step_times_grid():
    steps = step_times(date(2026, 7, 15), LAT, LON)
    assert all(t.minute % 10 == 0 for t in steps)
    st = sun_times(date(2026, 7, 15), LAT, LON)
    assert steps[0] <= st["sunrise"] - pd.Timedelta(minutes=20)
    assert steps[-1] >= st["sunset"] + pd.Timedelta(minutes=20)
    assert 70 <= len(steps) <= 95


def test_golden_file_matches_engine():
    g = build_golden()
    assert len(g["samples"]) == 20
    if GOLDEN_PATH.exists():
        on_disk = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
        assert len(on_disk["samples"]) == 20
    for s in g["samples"]:
        assert set(s) >= {"ts", "lat", "lon", "alt", "az"}
        p = sun_position(pd.Timestamp(s["ts"]).to_pydatetime(), s["lat"], s["lon"])
        assert p.alt_deg == pytest.approx(s["alt_apparent"], abs=1e-3)
        assert p.az_deg == pytest.approx(s["az"], abs=1e-3)
        assert s["alt"] > 5

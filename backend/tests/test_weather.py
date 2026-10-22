"""Weather module tests (no network: live is disabled)."""

from __future__ import annotations

from datetime import datetime

import pytest

from zill import weather
from zill.weather.fallback import apparent_temp, representative_day
from zill.weather.openmeteo import clear_sky_uv

T = "+04:00"


def test_clear_sky_uv_monotone_and_bounded():
    assert clear_sky_uv(0) == 0 and clear_sky_uv(-5) == 0
    assert clear_sky_uv(30) < clear_sky_uv(60) < clear_sky_uv(90) <= 12.5


def test_apparent_temp_hot_humid_exceeds_air():
    assert apparent_temp(40, 50, 3) > 40
    assert apparent_temp(20, 30, 5) < 20


def test_representative_day_is_labelled():
    from datetime import date

    d = representative_day(date(2026, 7, 15), 25.1972, 55.2744, "Asia/Dubai")
    assert d["synthetic_representative"] is True and "Not a measurement" in d["basis"]
    assert len(d["hourly"]) == 24
    temps = [r["temperature_2m"] for r in d["hourly"]]
    assert max(temps) > 40 and min(temps) < 33 and temps.index(max(temps)) in range(13, 18)


def test_get_cached_or_representative_has_source_and_alert():
    res = weather.get("dubai_downtown", datetime.fromisoformat("2026-07-15T14:00:00" + T), allow_live=False)
    assert res["source"] in ("cached", "representative")
    assert res["heat_alert"] is True and res["temperature_c"] > 38
    assert res["source"] != "cached" or "Recorded" in res["label"]


def test_get_winter_no_alert_and_unknown_date_representative():
    w = weather.get("dubai_downtown", datetime.fromisoformat("2026-01-15T13:00:00" + T), allow_live=False)
    assert w["heat_alert"] is False
    other = weather.get("dubai_downtown", datetime.fromisoformat("2027-02-02T13:00:00" + T), allow_live=False)
    assert other["source"] == "representative" and other["basis"]


def test_live_failure_falls_back(monkeypatch):
    import zill.weather.openmeteo as om

    def boom(*a, **k):
        raise TimeoutError("offline")

    monkeypatch.setattr(om, "fetch_day", boom)
    weather._live_mem.clear()
    res = weather.get("dubai_downtown", datetime.fromisoformat("2026-07-15T14:00:00" + T), allow_live=True)
    assert res["source"] in ("cached", "representative")


def test_live_path_uses_recorded_shape(monkeypatch):
    import zill.weather.openmeteo as om

    rows = [
        {
            "time": f"2026-07-15T{h:02d}:00",
            "temperature_2m": 30.0 + h / 2,
            "apparent_temperature": 33.0 + h / 2,
            "relative_humidity_2m": 50,
            "wind_speed_10m": 3.0,
            "uv_index": None,
            "uv_index_clear_sky": None,
        }
        for h in range(24)
    ]
    monkeypatch.setattr(
        om,
        "fetch_day",
        lambda *a, **k: {"api": "archive", "url": "x", "hourly": rows, "uv_basis": "clear_sky_estimate"},
    )
    weather._live_mem.clear()
    res = weather.get("dubai_downtown", datetime.fromisoformat("2026-07-15T12:30:00" + T), allow_live=True)
    assert res["source"] == "live" and res["temperature_c"] == pytest.approx(36.25, abs=0.05)
    assert res["uv_index"] is not None and res["uv_basis"] == "clear_sky_estimate"
    weather._live_mem.clear()

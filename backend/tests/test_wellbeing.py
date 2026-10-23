"""Well-being block (overnight Stream A): UV, heat stress, daylight window, breaks, overcast; weather."""

from __future__ import annotations

import math
from datetime import datetime

import pytest

from zill import wellbeing as W


@pytest.mark.parametrize(
    ("uv", "band"),
    [
        (0.0, "low"),
        (2.4, "low"),
        (2.6, "moderate"),
        (5.4, "moderate"),
        (6.0, "high"),
        (7.4, "high"),
        (8.0, "very high"),
        (10.4, "very high"),
        (11.0, "extreme"),
        (14.0, "extreme"),
    ],
)
def test_uv_bands_follow_who(uv, band):
    out = W.uv_band(uv, "uv_index_forecast")
    assert out["band"] == band and out["basis"] == "uv_index_forecast" and out["advice"]


def test_uv_unknown():
    assert W.uv_band(None)["band"] == "unknown"


@pytest.mark.parametrize(
    ("app", "band"),
    [
        (20.0, "none"),
        (26.7, "caution"),
        (32.0, "caution"),
        (32.2, "extreme caution"),
        (39.4, "danger"),
        (51.7, "extreme danger"),
    ],
)
def test_heat_bands_nws_indicative(app, band):
    out = W.heat_stress(app, rhl=123.456)
    assert out["band"] == band and out["indicative"] is True and out["route_rhl"] == 123.5


def test_shadow_ratio():
    assert W.shadow_ratio(45.0) == pytest.approx(1.0)
    assert W.shadow_ratio(30.0) == pytest.approx(math.sqrt(3))
    assert W.shadow_ratio(6.6) == pytest.approx(8.64, abs=0.01)  # Oslo midwinter noon
    assert W.shadow_ratio(0.0) is None and W.shadow_ratio(-5) is None


def test_daylight_window_open():
    out = W.daylight_window(60.0, 7.0, 10.0)
    assert out["active"] is True
    assert out["text"] == "Daylight / vitamin D window. Well-being guidance, not medical advice."
    assert out["shadow_text"] == "Your shadow is 0.6× your height."
    assert out["reasons"] == []


@pytest.mark.parametrize(
    ("alt", "uv", "cloud", "why"),
    [
        (40.0, 7.0, 10.0, "below 45 deg"),
        (60.0, 2.4, 10.0, "UV index 2.4"),
        (60.0, 7.0, 70.0, "cloud cover 70%"),
        (60.0, 7.0, None, "sky state unknown"),
        (-3.0, 0.0, 0.0, "below the horizon"),
    ],
)
def test_daylight_window_closed(alt, uv, cloud, why):
    out = W.daylight_window(alt, uv, cloud)
    assert out["active"] is False and why in out["text"]
    assert "vitamin D window now" in out["text"]


def test_breaks_every_n_minutes_of_direct_sun_when_hot():
    segs = [
        {"arrival_s": 0.0, "t_s": 400.0, "sun": 1.0, "cls": "open"},
        {"arrival_s": 400.0, "t_s": 300.0, "sun": 0.0, "cls": "covered"},
        {"arrival_s": 700.0, "t_s": 800.0, "sun": 1.0, "cls": "open"},
    ]
    out = W.break_prompts(segs, 1200.0, apparent_c=40.0, every_min=10)
    assert out["hot"] is True
    assert [p["at_s"] for p in out["prompts"]] == [900.0, 1500.0]
    assert out["prompts"][1]["sun_min"] == 20.0 and "not medical advice" in out["prompts"][0]["text"]
    assert W.break_prompts(segs, 1200.0, apparent_c=25.0)["prompts"] == []
    nogeo = W.break_prompts(None, 1250.0, apparent_c=40.0, every_min=10)
    assert [p["at_s"] for p in nogeo["prompts"]] == [None, None]


def test_overcast_only_in_sun_mode():
    assert W.overcast_note("sun", 85.0)["cloud_cover_pct"] == 85
    assert "little direct sun" in W.overcast_note("sun", 85.0)["text"]
    assert W.overcast_note("sun", 40.0) is None
    assert W.overcast_note("shade", 95.0) is None
    assert W.overcast_note("sun", None) is None


def test_assess_never_claims_treatment():
    w = {
        "uv_index": 9.0,
        "uv_basis": "uv_index_forecast",
        "apparent_c": 45.0,
        "cloud_cover_pct": 5.0,
        "source": "live",
        "label": "Live forecast data (Open-Meteo)",
    }
    out = W.assess("sun", 70.0, w, {"rhl": 500.0, "sun_exposure_s": 1300.0}, None)
    assert out["uv"]["band"] == "very high" and out["heat_stress"]["band"] == "danger"
    assert out["daylight_window"]["active"] is True and len(out["breaks"]["prompts"]) == 2
    assert out["weather"]["source"] == "live" and out["disclaimer"].endswith("not medical advice.")
    blob = repr(out).lower()
    assert "treat" not in blob and "cure" not in blob


# ---- weather ------------------------------------------------------------------------------------
T = "+04:00"


def test_recorded_weather_has_sky_fields_and_prefer_recorded_skips_network(monkeypatch):
    import zill.weather.openmeteo as om
    from zill import weather

    def boom(*a, **k):
        raise AssertionError("network must not be called when a recorded file exists")

    monkeypatch.setattr(om, "fetch_day", boom)
    weather._live_mem.clear()
    w = weather.get(
        "dubai_downtown",
        datetime.fromisoformat("2026-01-15T10:00:00" + T),
        allow_live=True,
        prefer_recorded=True,
    )
    assert w["source"] == "cached" and w["label"].startswith("Recorded weather")
    assert w["cloud_cover_pct"] is not None and 0 <= w["cloud_cover_pct"] <= 100
    assert w["shortwave_wm2"] is not None


def test_fetch_day_requests_cloud_and_radiation(monkeypatch):
    from datetime import date

    import zill.weather.openmeteo as om

    seen = {}

    class Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "hourly": {
                    "time": ["2026-01-15T10:00"],
                    "temperature_2m": [20],
                    "apparent_temperature": [19],
                    "relative_humidity_2m": [50],
                    "wind_speed_10m": [2],
                    "cloud_cover": [80],
                    "shortwave_radiation": [300],
                }
            }

    class Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, params):
            seen.update(params)
            return Resp()

    monkeypatch.setattr(om.httpx, "Client", Client)
    out = om.fetch_day(25.2, 55.3, date(2026, 1, 15), "Asia/Dubai", today=date(2026, 10, 23))
    assert "cloud_cover" in seen["hourly"] and "shortwave_radiation" in seen["hourly"]
    assert out["hourly"][0]["cloud_cover"] == 80 and out["hourly"][0]["shortwave_radiation"] == 300


def test_merge_sky_only_adds_sky_keys():
    from zill.weather.record import merge_sky

    rec = {"hourly": [{"time": "t0", "temperature_2m": 20.0}, {"time": "t1", "temperature_2m": 21.0}]}
    fetched = {
        "hourly": [{"time": "t0", "temperature_2m": 99.0, "cloud_cover": 50, "shortwave_radiation": 10}]
    }
    assert merge_sky(rec, fetched) == 1
    assert rec["hourly"][0] == {
        "time": "t0",
        "temperature_2m": 20.0,
        "cloud_cover": 50,
        "shortwave_radiation": 10,
    }
    assert "cloud_cover" not in rec["hourly"][1]


# ---- sky state: radiation (Haurwitz clear-sky index) first, cloud cover only as fallback ---------
def test_haurwitz_clear_sky_ghi():
    assert W.clear_sky_ghi(90.0) == pytest.approx(1098.0 * math.exp(-0.057), rel=1e-9)  # ~1037 W/m2
    assert W.clear_sky_ghi(30.0) == pytest.approx(1098.0 * 0.5 * math.exp(-0.114), rel=1e-9)
    assert W.clear_sky_ghi(0.0) == 0.0 and W.clear_sky_ghi(None) == 0.0
    assert W.clear_sky_index(None, 60.0) is None
    assert W.clear_sky_index(10.0, 1.0) is None  # clear-sky GHI below the 50 W/m2 floor: not judged
    assert W.clear_sky_index(W.clear_sky_ghi(60.0) / 2, 60.0) == pytest.approx(0.5)


def test_sky_state_radiation_beats_cloud_cover():
    thin_cirrus = W.sky_state(0.9, 100.0)  # bright sun under "100 %" (thin, high) cloud
    assert thin_cirrus["overcast"] is False and thin_cirrus["basis"] == "radiation"
    dark = W.sky_state(0.3, 20.0)
    assert dark["overcast"] is True and dark["basis"] == "radiation"
    assert W.sky_state(None, 75.0) == {**W.sky_state(None, 75.0), "overcast": True, "basis": "cloud_cover"}
    assert W.sky_state(None, None)["overcast"] is None


def test_overcast_and_window_use_radiation():
    assert W.overcast_note("sun", 100.0, 0.9) is None
    note = W.overcast_note("sun", 20.0, 0.25)
    assert note["basis"] == "radiation" and "25% of the clear-sky level" in note["text"]
    assert W.overcast_note("sun", 80.0, None)["basis"] == "cloud_cover"
    assert W.daylight_window(60.0, 7.0, 98.0, 0.92)["active"] is True
    closed = W.daylight_window(60.0, 7.0, 10.0, 0.3)
    assert closed["active"] is False and "clear-sky level" in closed["text"]
    assert closed["sky"]["basis"] == "radiation"


def test_recorded_winter_weather_is_bright_despite_cloud_cover():
    from zill import weather

    w = weather.get(
        "dubai_downtown",
        datetime.fromisoformat("2026-01-15T12:30:00" + T),
        allow_live=False,
        prefer_recorded=True,
    )
    assert w["cloud_cover_pct"] >= 90 and w["clear_sky_index"] > 0.8
    out = W.assess("sun", 43.7, w)
    assert out["overcast"] is None and out["daylight_window"]["sky"]["overcast"] is False

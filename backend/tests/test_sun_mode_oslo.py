"""Oslo sun mode (overnight Stream A): weather provenance (stand-in label, no Dubai climate) and the
documented sun-mode search results in data/scenarios/hero_oslo.json (real baked data)."""

from __future__ import annotations

import json

from zill import config


# ---- Oslo: weather provenance and the sun search (real baked data) ------------------------------
def test_oslo_weather_stand_in_and_no_dubai_climate():
    from datetime import date, datetime

    from zill import weather
    from zill.weather.fallback import representative_day

    w = weather.get(
        "oslo", datetime.fromisoformat("2026-12-21T12:30:00+01:00"), allow_live=False, prefer_recorded=True
    )
    assert w["source"] == "cached" and "stand-in for 2026-12-21" in w["label"] and "2025-12-21" in w["label"]
    assert w["apparent_c"] is not None and w["apparent_c"] < 10  # a real Oslo December value, not Dubai's
    rep = representative_day(date(2027, 1, 10), 59.91, 10.744, "Europe/Oslo")
    assert rep["synthetic_representative"] and all(r["temperature_2m"] is None for r in rep["hourly"])
    dubai = representative_day(date(2027, 1, 10), 25.2, 55.27, "Asia/Dubai")
    assert dubai["hourly"][12]["temperature_2m"] is not None


def test_oslo_hero_sun_block():
    path = config.DATA_DIR / "scenarios" / "hero_oslo.json"
    sun = json.loads(path.read_text(encoding="utf-8"))["sun"]
    assert sun["city"] == "oslo" and sun["search"]["procedure"].startswith("S8.")
    by = {sc["id"]: sc for sc in sun["scenarios"]}
    winter, summer = by["solstice_midday_walk"], by["summer_daylight_walk"]
    ww = winter["wellbeing"]["daylight_window"]
    assert winter["date_id"] == "winter" and ww["active"] is False and ww["sun_alt_deg"] < 8
    assert ww["shadow_ratio"] > 7  # shadows are many times your height at the solstice
    assert summer["wellbeing"]["daylight_window"]["active"] is True
    for sc in (winter, summer):
        st = sc["sunniest"]["stats"]
        assert (
            st["sun_gained_s"] > 0
            and st["added_time_s"] <= 0.25 * sc["fastest"]["stats"]["duration_s"] + 1e-6
        )

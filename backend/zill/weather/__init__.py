"""Weather and heat context (PRD 9): live -> cached -> representative.

`get(city_id, at)` returns a dict with `source` in {"live", "cached", "representative"}, the hourly
series interpolated at `at`, and a `heat_alert` flag (apparent >= 40 C or UV >= 8).
Weather never changes shadow geometry.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from zill import config

log = logging.getLogger(__name__)

HEAT_APPARENT_C = 40.0
HEAT_UV = 8.0
CACHE_DIR = config.DATA_DIR / "weather_cache"
_LIVE_TTL_S = 600.0
_live_mem: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}


def _live_enabled() -> bool:
    if config.REPLAY:
        return False
    return os.environ.get("ZILL_WEATHER_LIVE", "1").strip().lower() not in ("0", "false", "no", "off")


def _city_info(city_id: str) -> dict[str, Any]:
    from zill.services import CityNotFound, city_dir

    try:
        meta = json.loads((city_dir(city_id) / "meta.json").read_text(encoding="utf-8"))
    except (CityNotFound, FileNotFoundError):
        if city_id != config.DEFAULT_CITY:
            raise
        # default city not baked yet: fall back to the config constants (weather needs only lat/lon)
        meta = {"origin": {"lat": config.ORIGIN_LAT, "lon": config.ORIGIN_LON}}
    return {
        "lat": meta["origin"]["lat"],
        "lon": meta["origin"]["lon"],
        "tz": meta.get("timezone", config.TIMEZONE),
        "dates": meta.get("dates") or config.PRESET_DATES,
    }


def cache_path(city_id: str, date_id: str) -> Path:
    return CACHE_DIR / f"{city_id}_{date_id}.json"


def date_id_for(dates: dict[str, str], day: date) -> str:
    iso = day.isoformat()
    for k, v in dates.items():
        if v == iso:
            return k
    return iso


def load_recorded(city_id: str, date_id: str) -> dict[str, Any] | None:
    p = cache_path(city_id, date_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def build_record(city_id: str, day: date, fetched: dict[str, Any], info: dict[str, Any]) -> dict[str, Any]:
    """Normalise a fetched day: fill missing UV with the labelled clear-sky estimate."""
    from zill.sun.position import sun_positions
    from zill.weather.openmeteo import clear_sky_uv

    tz = ZoneInfo(info["tz"])
    rows = fetched["hourly"]
    times = [datetime.fromisoformat(r["time"]).replace(tzinfo=tz) for r in rows]
    alts = [p.alt_deg for p in sun_positions(times, info["lat"], info["lon"], info["tz"])]
    filled = 0
    for r, a in zip(rows, alts, strict=True):
        if r.get("uv_index") is None:
            r["uv_index"] = clear_sky_uv(a)
            filled += 1
    basis = fetched.get("uv_basis", "uv_index_forecast")
    if filled == len(rows):
        basis = "clear_sky_estimate"
    return {
        "city": city_id,
        "date": day.isoformat(),
        "lat": info["lat"],
        "lon": info["lon"],
        "tz": info["tz"],
        "synthetic_representative": False,
        "source_api": fetched.get("api"),
        "source_url": fetched.get("url"),
        "fetched_at": datetime.now(ZoneInfo(info["tz"])).isoformat(timespec="seconds"),
        "uv_basis": basis,
        "hourly": rows,
    }


def _interp(rows: list[dict[str, Any]], at: datetime, key: str) -> float | None:
    pts = []
    for r in rows:
        v = r.get(key)
        if v is None:
            continue
        pts.append((datetime.fromisoformat(r["time"]).replace(tzinfo=None), float(v)))
    if not pts:
        return None
    t = at.replace(tzinfo=None)
    if t <= pts[0][0]:
        return pts[0][1]
    for (t0, v0), (t1, v1) in zip(pts, pts[1:], strict=False):
        if t0 <= t <= t1:
            f = (t - t0).total_seconds() / (t1 - t0).total_seconds()
            return v0 + (v1 - v0) * f
    return pts[-1][1]


def _label(source: str, rec: dict[str, Any], day: date) -> str:
    if source == "representative":
        return f"Representative {day.strftime('%B')} profile (not a measurement)"
    if source == "live":
        return f"Live {rec.get('source_api', 'forecast')} data (Open-Meteo)"
    return f"Recorded weather for {day.isoformat()} (Open-Meteo {rec.get('source_api', 'archive')})"


def _clear_sky_index_at(rows: list[dict[str, Any]], at: datetime, info: dict[str, Any]) -> float | None:
    """Clear-sky index (measured / Haurwitz clear-sky GHI) per hourly row, interpolated at `at`.

    Open-Meteo `shortwave_radiation` is the mean over the PRECEDING hour, so each row is compared with
    the clear-sky GHI at the middle of that hour (row time - 30 min).
    """
    from datetime import timedelta

    from zill.sun.position import sun_positions
    from zill.wellbeing import clear_sky_index

    if not any(r.get("shortwave_radiation") is not None for r in rows):
        return None
    tz = ZoneInfo(info["tz"])
    mids = [datetime.fromisoformat(r["time"]).replace(tzinfo=tz) - timedelta(minutes=30) for r in rows]
    alts = [p.alt_deg for p in sun_positions(mids, info["lat"], info["lon"], info["tz"])]
    pts = [
        {"time": r["time"], "kt": clear_sky_index(r.get("shortwave_radiation"), a)}
        for r, a in zip(rows, alts, strict=True)
    ]
    return _interp(pts, at, "kt")


def get(
    city_id: str,
    at: datetime | None = None,
    allow_live: bool | None = None,
    prefer_recorded: bool = False,
) -> dict[str, Any]:
    """Weather at `at`. `prefer_recorded=True` (route responses) uses a recorded file for the date when
    one exists and only then tries live, so routing never waits on the network for preset dates."""
    info = _city_info(city_id)
    tz = ZoneInfo(info["tz"])
    at = at.astimezone(tz) if at and at.tzinfo else (at.replace(tzinfo=tz) if at else datetime.now(tz))
    day = at.date()
    did = date_id_for(info["dates"], day)
    rec: dict[str, Any] | None = None
    source = "representative"

    live_ok = _live_enabled() if allow_live is None else allow_live
    if prefer_recorded:
        rec = load_recorded(city_id, did)
        if rec is not None:
            source = "representative" if rec.get("synthetic_representative") else "cached"
            live_ok = False
    if live_ok:
        key = (city_id, day.isoformat())
        hit = _live_mem.get(key)
        if hit and time.time() - hit[0] < _LIVE_TTL_S:
            rec, source = hit[1], "live"
        else:
            try:
                from zill.weather.openmeteo import fetch_day

                fetched = fetch_day(info["lat"], info["lon"], day, info["tz"], timeout_s=2.0)
                rec = build_record(city_id, day, fetched, info)
                _live_mem[key] = (time.time(), rec)
                source = "live"
            except Exception as e:  # offline / slow / rate limited -> fall back quietly
                log.info("live weather unavailable (%s); using recorded/representative", type(e).__name__)
                rec = None
    if rec is None:
        rec = load_recorded(city_id, did)
        if rec is not None:
            source = "representative" if rec.get("synthetic_representative") else "cached"
    if rec is None:
        from zill.weather.fallback import representative_day

        rec = representative_day(day, info["lat"], info["lon"], info["tz"])
        source = "representative"

    rows = rec["hourly"]
    t = _interp(rows, at, "temperature_2m")
    app = _interp(rows, at, "apparent_temperature")
    rh = _interp(rows, at, "relative_humidity_2m")
    uv = _interp(rows, at, "uv_index")
    wind = _interp(rows, at, "wind_speed_10m")
    cloud = _interp(rows, at, "cloud_cover")
    sw = _interp(rows, at, "shortwave_radiation")
    kt = _clear_sky_index_at(rows, at, info)
    alert = bool((app is not None and app >= HEAT_APPARENT_C) or (uv is not None and uv >= HEAT_UV))
    out = {
        "city": city_id,
        "at": at.isoformat(),
        "source": source,
        "temperature_c": None if t is None else round(t, 1),
        "apparent_c": None if app is None else round(app, 1),
        "humidity_pct": None if rh is None else round(rh),
        "uv_index": None if uv is None else round(uv, 1),
        "uv_basis": rec.get("uv_basis", "uv_index_forecast"),
        "wind_ms": None if wind is None else round(wind, 1),
        "cloud_cover_pct": None if cloud is None else round(cloud),
        "shortwave_wm2": None if sw is None else round(sw),
        "clear_sky_index": None if kt is None else round(kt, 2),
        "heat_alert": alert,
        "label": _label(source, rec, day),
        "hourly": rows,
    }
    if rec.get("synthetic_representative"):
        out["basis"] = rec.get("basis")
    if source == "cached":
        out["fetched_at"] = rec.get("fetched_at")
    return out

"""Record weather files for the preset dates: python -m zill.weather.record [--city dubai_downtown].

`--add-sky` only merges hourly `cloud_cover` / `shortwave_radiation` into the existing recorded files
(other values untouched; provenance in `sky_source_api` / `sky_fetched_at`).

Real Open-Meteo data when reachable; otherwise a representative profile marked
`"synthetic_representative": true` with a `basis` string.
"""

from __future__ import annotations

import argparse
import json
from datetime import date

from zill import config
from zill.weather import CACHE_DIR, _city_info, build_record, cache_path
from zill.weather.fallback import representative_day
from zill.weather.openmeteo import fetch_day


def stand_in_record(city_id: str, day: date, info: dict) -> dict:
    """Future date beyond the forecast horizon: the same date one year earlier from the archive, re-dated to
    `day` and labelled (`stand_in_from`). Real measurements of another year, never invented values."""
    prev = day.replace(year=day.year - 1)
    fetched = fetch_day(info["lat"], info["lon"], prev, info["tz"], timeout_s=20.0)
    for r in fetched["hourly"]:
        r["time"] = day.isoformat() + r["time"][10:]
    rec = build_record(city_id, day, fetched, info)
    rec["stand_in_from"] = prev.isoformat()
    rec["stand_in_note"] = (
        f"No forecast exists for {day.isoformat()} yet; values are Open-Meteo archive data for "
        f"{prev.isoformat()} (same date a year earlier), clearly labelled as a stand-in."
    )
    return rec


def record(city_id: str) -> dict[str, str]:
    info = _city_info(city_id)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out: dict[str, str] = {}
    for did, iso in info["dates"].items():
        day = date.fromisoformat(iso)
        try:
            try:
                fetched = fetch_day(info["lat"], info["lon"], day, info["tz"], timeout_s=20.0)
                rec = build_record(city_id, day, fetched, info)
                out[did] = f"real ({fetched['api']}, uv: {rec['uv_basis']})"
            except Exception:
                if day <= date.today():
                    raise
                rec = stand_in_record(city_id, day, info)
                out[did] = f"stand-in: archive {rec['stand_in_from']} (uv: {rec['uv_basis']})"
        except Exception as e:
            rec = {
                "city": city_id,
                "date": iso,
                "lat": info["lat"],
                "lon": info["lon"],
                "tz": info["tz"],
                **representative_day(day, info["lat"], info["lon"], info["tz"]),
            }
            out[did] = f"representative ({type(e).__name__})"
        cache_path(city_id, did).write_text(json.dumps(rec, indent=1), encoding="utf-8")
    return out


SKY_KEYS = ("cloud_cover", "shortwave_radiation")


def merge_sky(rec: dict, fetched: dict) -> int:
    """Copy SKY_KEYS from fetched hourly rows into rec's rows with the same `time`. Returns rows filled."""
    by_t = {r["time"]: r for r in fetched["hourly"]}
    n = 0
    for r in rec["hourly"]:
        f = by_t.get(r["time"])
        if f is None:
            continue
        for k in SKY_KEYS:
            if f.get(k) is not None:
                r[k] = f[k]
        n += 1
    return n


def add_sky(city_id: str) -> dict[str, str]:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    info = _city_info(city_id)
    out: dict[str, str] = {}
    for did, iso in info["dates"].items():
        p = cache_path(city_id, did)
        if not p.exists():
            out[did] = "no recorded file"
            continue
        rec = json.loads(p.read_text(encoding="utf-8"))
        if rec.get("synthetic_representative"):
            out[did] = "representative profile: skipped (no sky data invented)"
            continue
        try:
            fetched = fetch_day(info["lat"], info["lon"], date.fromisoformat(iso), info["tz"], timeout_s=20.0)
        except Exception as e:
            out[did] = f"fetch failed ({type(e).__name__})"
            continue
        n = merge_sky(rec, fetched)
        rec["sky_source_api"] = fetched.get("api")
        rec["sky_fetched_at"] = datetime.now(ZoneInfo(info["tz"])).isoformat(timespec="seconds")
        p.write_text(json.dumps(rec, indent=1), encoding="utf-8")
        out[did] = f"sky merged into {n} rows ({fetched.get('api')})"
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default=config.DEFAULT_CITY)
    ap.add_argument("--add-sky", action="store_true")
    a = ap.parse_args()
    for k, v in (add_sky(a.city) if a.add_sky else record(a.city)).items():
        print(f"{k}: {v}")

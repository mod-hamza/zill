"""Record weather files for the preset dates: python -m zill.weather.record [--city dubai_downtown].

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


def record(city_id: str) -> dict[str, str]:
    info = _city_info(city_id)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out: dict[str, str] = {}
    for did, iso in info["dates"].items():
        day = date.fromisoformat(iso)
        try:
            fetched = fetch_day(info["lat"], info["lon"], day, info["tz"], timeout_s=20.0)
            rec = build_record(city_id, day, fetched, info)
            out[did] = f"real ({fetched['api']}, uv: {rec['uv_basis']})"
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


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default=config.DEFAULT_CITY)
    for k, v in record(ap.parse_args().city).items():
        print(f"{k}: {v}")

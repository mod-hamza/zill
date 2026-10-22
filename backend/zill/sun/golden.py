"""Generate `data/curated/sun_golden.json` from pvlib (PRD 7.1).

`alt` is the geometric (refraction-free) elevation so the frontend `suncalc` test compares like
with like; `alt_apparent` (what the shade engine uses) is stored alongside.

Run: python -m zill.sun.golden
"""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pvlib

from zill import config

GOLDEN_PATH = config.DATA_DIR / "curated" / "sun_golden.json"

# 4 preset dates x 3 times + 4 other dates x 2 times = 20 timestamps (all well above the horizon).
_SAMPLES: list[tuple[str, list[str]]] = [
    (config.PRESET_DATES["winter"], ["09:00", "12:30", "16:00"]),
    (config.PRESET_DATES["spring"], ["08:30", "12:20", "17:00"]),
    (config.PRESET_DATES["summer"], ["07:30", "13:30", "17:40"]),
    (config.PRESET_DATES["hackathon"], ["08:00", "12:00", "16:00"]),
    ("2026-03-20", ["10:00", "15:30"]),
    ("2026-06-21", ["12:20", "18:00"]),
    ("2026-09-22", ["07:40", "14:10"]),
    ("2026-12-21", ["12:20", "16:30"]),
]


def build_golden(lat: float = config.ORIGIN_LAT, lon: float = config.ORIGIN_LON) -> dict:
    zi = ZoneInfo(config.TIMEZONE)
    stamps = [
        datetime.fromisoformat(f"{d}T{t}:00").replace(tzinfo=zi) for d, times in _SAMPLES for t in times
    ]
    sp = pvlib.solarposition.get_solarposition(pd.DatetimeIndex(stamps), lat, lon)
    rows = []
    for ts, (_, r) in zip(stamps, sp.iterrows(), strict=True):
        rows.append({
            "ts": ts.isoformat(),
            "lat": lat,
            "lon": lon,
            "alt": round(float(r["elevation"]), 4),
            "alt_apparent": round(float(r["apparent_elevation"]), 4),
            "az": round(float(r["azimuth"]), 4),
        })
    return {
        "generated_by": "pvlib.solarposition.get_solarposition (NREL SPA)",
        "pvlib_version": pvlib.__version__,
        "note": "alt = geometric elevation (no refraction, suncalc-comparable); az clockwise from north",
        "samples": rows,
    }


def main() -> None:
    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN_PATH.write_text(json.dumps(build_golden(), indent=2), encoding="utf-8")
    print(f"wrote {GOLDEN_PATH}")


if __name__ == "__main__":
    main()

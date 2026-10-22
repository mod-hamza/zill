"""Representative (synthetic) weather profiles, clearly labelled (PRD 9).

Used only when neither live nor recorded data exist. Values are a smooth diurnal curve around
approximate monthly Dubai highs/lows: NOT a measurement. Every profile carries
`synthetic_representative: true` and a `basis` string, and the UI must show it as such.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any

# month -> (daily min C, daily max C, afternoon RH %, dawn RH %, mean wind m/s)
# Approximate climatology, [TEAM TO FILL - cite source] (listed in docs/OPEN_ITEMS.md).
_CLIMATE = {
    1: (14, 24, 50, 80, 3.5),
    2: (15, 25, 48, 80, 3.8),
    3: (18, 29, 45, 78, 4.0),
    4: (22, 34, 38, 72, 4.2),
    5: (26, 39, 35, 70, 4.2),
    6: (29, 41, 40, 74, 4.2),
    7: (31, 42, 45, 78, 4.0),
    8: (31, 42, 48, 80, 3.8),
    9: (28, 40, 48, 80, 3.6),
    10: (24, 36, 45, 80, 3.4),
    11: (19, 31, 48, 80, 3.2),
    12: (16, 26, 50, 80, 3.2),
}


def apparent_temp(t_c: float, rh_pct: float, wind_ms: float) -> float:
    """Australian BoM apparent temperature: AT = T + 0.33 e - 0.70 ws - 4.00."""
    e = rh_pct / 100.0 * 6.105 * math.exp(17.27 * t_c / (237.7 + t_c))
    return t_c + 0.33 * e - 0.70 * wind_ms - 4.0


def representative_day(day: date, lat: float, lon: float, tz: str) -> dict[str, Any]:
    from zill.weather.openmeteo import clear_sky_uv

    tmin, tmax, rh_aft, rh_dawn, wind = _CLIMATE[day.month]
    rows = []
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from zill.sun.position import sun_positions

    times = [datetime(day.year, day.month, day.day, h, tzinfo=ZoneInfo(tz)) for h in range(24)]
    alts = [p.alt_deg for p in sun_positions(times, lat, lon, tz)]
    for h in range(24):
        # temperature: minimum ~05:30, maximum ~15:30 (smooth cosine)
        phase = math.cos((h - 15.5) / 24.0 * 2 * math.pi)
        t = tmin + (tmax - tmin) * (0.5 + 0.5 * phase)
        rh = rh_dawn + (rh_aft - rh_dawn) * (0.5 + 0.5 * phase)
        w = wind * (0.8 + 0.4 * (0.5 + 0.5 * phase))
        rows.append(
            {
                "time": (times[h].replace(tzinfo=None)).isoformat(timespec="minutes"),
                "temperature_2m": round(t, 1),
                "apparent_temperature": round(apparent_temp(t, rh, w), 1),
                "relative_humidity_2m": round(rh),
                "wind_speed_10m": round(w, 1),
                "uv_index": clear_sky_uv(alts[h]),
                "uv_index_clear_sky": clear_sky_uv(alts[h]),
            }
        )
    return {
        "synthetic_representative": True,
        "basis": (
            f"Representative {day.strftime('%B')} profile for Dubai: smooth diurnal curve between "
            f"approximate climatological low {tmin} C and high {tmax} C; apparent temperature by the "
            "BoM formula; UV is a "
            "clear-sky estimate from solar altitude. Not a measurement. [TEAM TO FILL - cite source]"
        ),
        "uv_basis": "clear_sky_estimate",
        "hourly": rows,
    }

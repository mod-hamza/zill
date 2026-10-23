"""Open-Meteo client (PRD 9). No API key. Hourly series for one local date.

* Past dates -> archive API (no UV there; a clearly-labelled clear-sky estimate is added).
* Today / future (within the forecast horizon) -> forecast API (has uv_index + uv_index_clear_sky).
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any

import httpx

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
UA = {"User-Agent": "Zill-hackathon-prototype/0.1"}
HOURLY_BASE = "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m"
# overnight Stream A: cloud cover (%) and global horizontal irradiance (W/m2); both archive + forecast
HOURLY_SKY = "cloud_cover,shortwave_radiation"


def clear_sky_uv(alt_deg: float) -> float:
    """Clear-sky UV index estimate from solar altitude: 12.5 * sin(alt)^2.42 (rough; not a measurement)."""
    s = math.sin(math.radians(max(alt_deg, 0.0)))
    return round(12.5 * s**2.42, 2)


def fetch_day(
    lat: float, lon: float, day: date, tz: str, timeout_s: float = 8.0, today: date | None = None
) -> dict[str, Any]:
    """Fetch one local date. Returns {'api','uv_basis','hourly':[...]} (raises httpx errors)."""
    today = today or datetime.now().date()
    past = day < today - timedelta(days=2)
    url = ARCHIVE_URL if past else FORECAST_URL
    hourly = HOURLY_BASE + "," + HOURLY_SKY + ("" if past else ",uv_index,uv_index_clear_sky")
    params = {
        "latitude": f"{lat:.4f}",
        "longitude": f"{lon:.4f}",
        "hourly": hourly,
        "timezone": tz,
        "wind_speed_unit": "ms",
        "start_date": day.isoformat(),
        "end_date": day.isoformat(),
    }
    with httpx.Client(timeout=timeout_s, headers=UA) as c:
        r = c.get(url, params=params)
        r.raise_for_status()
        j = r.json()
    h = j["hourly"]
    rows = []
    for i, t in enumerate(h["time"]):
        rows.append(
            {
                "time": t,
                "temperature_2m": h["temperature_2m"][i],
                "apparent_temperature": h["apparent_temperature"][i],
                "relative_humidity_2m": h["relative_humidity_2m"][i],
                "wind_speed_10m": h["wind_speed_10m"][i],
                "uv_index": (h.get("uv_index") or [None] * len(h["time"]))[i],
                "uv_index_clear_sky": (h.get("uv_index_clear_sky") or [None] * len(h["time"]))[i],
                "cloud_cover": (h.get("cloud_cover") or [None] * len(h["time"]))[i],
                "shortwave_radiation": (h.get("shortwave_radiation") or [None] * len(h["time"]))[i],
            }
        )
    return {
        "api": "archive" if past else "forecast",
        "url": url,
        "hourly": rows,
        "uv_basis": "uv_index_forecast" if not past else "clear_sky_estimate",
    }

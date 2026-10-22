"""Sun position (PRD 7.1). Azimuth is clockwise from north; altitude is apparent elevation.

Local frame (PRD 6.1): x = east, y = up, z = south (north = -z). The unit vector pointing
TOWARD the sun is (sin(az)cos(alt), sin(alt), -cos(az)cos(alt)).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pvlib

from zill import config


@dataclass(frozen=True)
class SunPos:
    alt_deg: float
    az_deg: float

    @property
    def vector(self) -> tuple[float, float, float]:
        return sun_vector(self.alt_deg, self.az_deg)

    @property
    def is_night(self) -> bool:
        return self.alt_deg <= config.SUN_MIN_ALT_DEG


def sun_vector(alt_deg: float, az_deg: float) -> tuple[float, float, float]:
    """Unit vector toward the sun in the local frame (x east, y up, z south)."""
    a = math.radians(alt_deg)
    z = math.radians(az_deg)
    return (math.sin(z) * math.cos(a), math.sin(a), -math.cos(z) * math.cos(a))


def _aware(ts: datetime, tz: str) -> datetime:
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=ZoneInfo(tz))


def sun_positions(times: list[datetime], lat: float, lon: float, tz: str = config.TIMEZONE) -> list[SunPos]:
    """Vectorised sun positions for many timestamps (naive ones are interpreted in `tz`)."""
    idx = pd.DatetimeIndex([_aware(t, tz) for t in times])
    sp = pvlib.solarposition.get_solarposition(idx, lat, lon)
    alts = sp["apparent_elevation"].to_numpy(dtype=float)
    azs = sp["azimuth"].to_numpy(dtype=float)
    return [SunPos(float(a), float(z)) for a, z in zip(alts, azs, strict=True)]


def sun_position(ts: datetime, lat: float, lon: float, tz: str = config.TIMEZONE) -> SunPos:
    return sun_positions([ts], lat, lon, tz)[0]


def sun_times(d: date, lat: float, lon: float, tz: str = config.TIMEZONE) -> dict[str, datetime]:
    """Sunrise, sunset and solar noon (timezone-aware, in `tz`) for local date `d`."""
    zi = ZoneInfo(tz)
    midnight = pd.DatetimeIndex([datetime(d.year, d.month, d.day, tzinfo=zi)])
    res = pvlib.solarposition.sun_rise_set_transit_spa(midnight, lat, lon)
    out: dict[str, datetime] = {}
    for key, col in (("sunrise", "sunrise"), ("sunset", "sunset"), ("solar_noon", "transit")):
        v = res[col].iloc[0]
        out[key] = pd.Timestamp(v).tz_convert(zi).round("s").to_pydatetime()
    return out


def step_times(d: date, lat: float, lon: float, tz: str = config.TIMEZONE,
               step_min: int = config.TIME_STEP_MIN, pad_min: int = 20) -> list[datetime]:
    """10-minute steps from floor(sunrise - pad) to ceil(sunset + pad) (PRD 7.4)."""
    st = sun_times(d, lat, lon, tz)
    zi = ZoneInfo(tz)
    day0 = datetime(d.year, d.month, d.day, tzinfo=zi)
    start_min = (st["sunrise"] - timedelta(minutes=pad_min) - day0).total_seconds() / 60.0
    end_min = (st["sunset"] + timedelta(minutes=pad_min) - day0).total_seconds() / 60.0
    m0 = int(math.floor(start_min / step_min) * step_min)
    m1 = int(math.ceil(end_min / step_min) * step_min)
    return [day0 + timedelta(minutes=int(m)) for m in np.arange(m0, m1 + 1, step_min)]

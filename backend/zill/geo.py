"""Local metric frame (PRD 6.1 / CONTRACTS 2). x = east, y = up, z = south.

Mirrored in frontend/src/lib/geo.ts. Origin is a (lat, lon) pair, an object with .lat/.lon,
or a dict with "lat"/"lon".
"""

from __future__ import annotations

import math
from typing import Any

M_PER_DEG_LON_EQ = 111320.0
M_PER_DEG_LAT = 110574.0


def _lat_lon(origin: Any) -> tuple[float, float]:
    if isinstance(origin, dict):
        return float(origin["lat"]), float(origin["lon"])
    if hasattr(origin, "lat"):
        return float(origin.lat), float(origin.lon)
    return float(origin[0]), float(origin[1])


def to_local(lat, lon, origin):
    """WGS84 -> local metres (x, z). Works on scalars and numpy arrays."""
    lat0, lon0 = _lat_lon(origin)
    cos0 = math.cos(math.radians(lat0))
    return (lon - lon0) * M_PER_DEG_LON_EQ * cos0, -(lat - lat0) * M_PER_DEG_LAT


def to_wgs84(x, z, origin):
    """Local metres (x, z) -> (lat, lon)."""
    lat0, lon0 = _lat_lon(origin)
    cos0 = math.cos(math.radians(lat0))
    return lat0 - z / M_PER_DEG_LAT, lon0 + x / (M_PER_DEG_LON_EQ * cos0)

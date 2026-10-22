"""Explain a shadow for the agent: which building casts it (PRD 11.6 tool support)."""

from __future__ import annotations

import math
from typing import Any

from zill import config
from zill.shade.cache import get_city_shade
from zill.shade.heightmap import CasterGrid


def first_blocker(caster: CasterGrid, x: float, z: float, alt_deg: float, az_deg: float,
                  h0: float = config.H0, max_dist: float = config.MAX_SHADOW_M,
                  ) -> tuple[int, float] | None:
    """(building_id, horizontal distance m) of the first building the sun ray hits, or None.

    Mirrors the raymarch kernel's blocking rule (disc centre only).
    """
    if alt_deg <= config.SUN_MIN_ALT_DEG:
        return None
    spec = caster.spec
    t = math.tan(math.radians(alt_deg))
    zr = math.radians(az_deg)
    drow, dcol = -math.cos(zr), math.sin(zr)
    r0 = (z - spec.z0) / spec.res - 0.5
    c0 = (x - spec.x0) / spec.res - 0.5
    half = 0.5 * spec.res * t
    for k in range(1, int(max_dist / spec.res) + 1):
        r = int(math.floor(r0 + k * drow + 0.5))
        c = int(math.floor(c0 + k * dcol + 0.5))
        if not (0 <= r < spec.rows and 0 <= c < spec.cols):
            return None
        hc = h0 + k * spec.res * t
        if hc - half > caster.max_height:
            return None
        hm = float(caster.hmax[r, c])
        if hm <= 0:
            continue
        hb = float(caster.hmin[r, c])
        blocked = hm > hc if hb <= h0 else (hm > hc - half and hb <= hc + half)
        if blocked:
            return int(caster.bid[r, c]), k * spec.res
    return None


def casting_building(city_id: str, x: float, z: float, alt_deg: float, az_deg: float,
                     ) -> dict[str, Any] | None:
    """{building_id, name, height, distance_m} of the building shading local point (x, z), or None."""
    sc = get_city_shade(city_id)
    hit = first_blocker(sc.caster, x, z, alt_deg, az_deg)
    if hit is None:
        return None
    bid, dist = hit
    b = sc.buildings_by_id().get(bid, {})
    return {"building_id": bid, "name": b.get("name"), "height": b.get("height"),
            "distance_m": round(dist, 1)}

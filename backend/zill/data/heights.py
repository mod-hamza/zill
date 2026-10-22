"""Building height rules (PRD 6.4), in priority order.

1. building:part polygons replace their shell (handled in buildings.py).
2. ``height`` tag ("m", "ft", "'" units or plain numbers); ``min_height`` honoured.
3. ``building:levels`` x 3.4 m (+ ``roof:levels`` x 3.0 m).
4. Fallback by building tag.
5. Curated landmark overrides always win (applied in buildings.py).
"""

from __future__ import annotations

import re
from typing import Any

LEVEL_H_M = 3.4
ROOF_LEVEL_H_M = 3.0
MIN_LEVEL_H_M = 0.0
FALLBACK_BY_TAG = {
    "apartments": 30.0,
    "residential": 30.0,
    "hotel": 45.0,
    "commercial": 40.0,
    "office": 40.0,
    "retail": 22.0,
    "mall": 22.0,
    "garage": 12.0,
    "garages": 12.0,
    "parking": 12.0,
}
FALLBACK_DEFAULT_M = 18.0
# Small structures that are clearly not 18 m tall if untagged (conservative, logged in DECISIONS).
FALLBACK_SMALL = {
    "roof": 6.0,
    "shed": 3.0,
    "kiosk": 3.0,
    "hut": 3.0,
    "carport": 4.0,
    "gatehouse": 4.0,
    "toilets": 4.0,
    "service": 6.0,
    "transformer_tower": 4.0,
    "construction": 18.0,
}
FT_TO_M = 0.3048

_NUM = re.compile(r"[-+]?\d+(?:[.,]\d+)?")


def parse_length(value: Any) -> float | None:
    """Parse an OSM length: '828', '828 m', '828m', '2717 ft', "2717'", '12'6"' (ft+in). None if invalid."""
    if value is None:
        return None
    s = str(value).strip().lower().replace(",", ".")
    if not s:
        return None
    s = s.split(";")[0].strip()
    ft_in = re.fullmatch(r"(\d+(?:\.\d+)?)\s*'\s*(?:(\d+(?:\.\d+)?)\s*\")?", s)
    if ft_in:
        feet = float(ft_in.group(1))
        inches = float(ft_in.group(2) or 0.0)
        return feet * FT_TO_M + inches * 0.0254
    m = _NUM.search(s)
    if not m:
        return None
    v = float(m.group(0))
    rest = s[m.end() :].strip()
    if rest.startswith(("ft", "feet", "foot")):
        v *= FT_TO_M
    elif rest.startswith("km"):
        v *= 1000.0
    elif rest and not rest.startswith(("m", "meter", "metre")):
        return None
    if v < 0 or v > 1500:
        return None
    return v


def parse_levels(value: Any) -> float | None:
    if value is None:
        return None
    m = _NUM.search(str(value).replace(",", "."))
    if not m:
        return None
    v = float(m.group(0))
    return v if 0 <= v <= 250 else None


def building_height(tags: dict[str, str]) -> tuple[float, float, str]:
    """Return (height_m, min_height_m, source) with source in tag|levels|fallback."""
    min_h = parse_length(tags.get("min_height"))
    if min_h is None:
        ml = parse_levels(tags.get("building:min_level"))
        min_h = ml * LEVEL_H_M if ml is not None else 0.0
    h = parse_length(tags.get("height"))
    if h is not None and h > 0:
        return h, min(min_h, h), "tag"
    lv = parse_levels(tags.get("building:levels"))
    if lv is not None and lv > 0:
        rl = parse_levels(tags.get("roof:levels")) or 0.0
        # Simple 3D Buildings: building:levels counts from the ground (incl. skipped min_level).
        h = lv * LEVEL_H_M + rl * ROOF_LEVEL_H_M
        if h <= min_h:
            h = min_h + LEVEL_H_M
        return h, min_h, "levels"
    btag = (tags.get("building") or tags.get("building:part") or "yes").lower()
    if btag in FALLBACK_SMALL:
        h = FALLBACK_SMALL[btag]
    else:
        h = FALLBACK_BY_TAG.get(btag, FALLBACK_DEFAULT_M)
    if min_h >= h:
        h = min_h + 3.0
    return h, min_h, "fallback"

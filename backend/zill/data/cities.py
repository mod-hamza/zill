"""City registry (`data/cities.json`) and bbox helpers. No city-specific code lives here."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from zill import config
from zill.geo import M_PER_DEG_LAT, M_PER_DEG_LON_EQ

REGISTRY = config.DATA_DIR / "cities.json"


@dataclass(frozen=True)
class CitySpec:
    city_id: str
    name: str
    bbox: dict[str, float]  # core bbox (WGS84)
    origin: dict[str, float]
    timezone: str
    # Optional per-city overrides (generic; absent for Dubai -> config defaults). High-latitude cities
    # need a wider caster ring: at 6.6 deg sun a building's shadow is ~8.6x its height.
    caster_buffer_m: float = config.CASTER_BUFFER_M
    dates: dict[str, str] | None = None

    @property
    def bbox_caster(self) -> dict[str, float]:
        return expand_bbox(self.bbox, self.caster_buffer_m)

    @property
    def preset_dates(self) -> dict[str, str]:
        return dict(self.dates or config.PRESET_DATES)

    @property
    def bbox_scene(self) -> dict[str, float]:
        return expand_bbox(self.bbox, config.SCENE_MARGIN_M)


def expand_bbox(b: dict[str, float], metres: float) -> dict[str, float]:
    lat_mid = (b["s"] + b["n"]) / 2
    dlat = metres / M_PER_DEG_LAT
    dlon = metres / (M_PER_DEG_LON_EQ * math.cos(math.radians(lat_mid)))
    return {
        "s": round(b["s"] - dlat, 6),
        "w": round(b["w"] - dlon, 6),
        "n": round(b["n"] + dlat, 6),
        "e": round(b["e"] + dlon, 6),
    }


def load_registry(path: Path | None = None) -> list[dict[str, Any]]:
    return json.loads((path or REGISTRY).read_text(encoding="utf-8"))


def get_city_spec(city_id: str, path: Path | None = None) -> CitySpec:
    for c in load_registry(path):
        if c["city_id"] == city_id:
            return CitySpec(
                c["city_id"],
                c["name"],
                c["bbox"],
                c["origin"],
                c["timezone"],
                float(c.get("caster_buffer_m", config.CASTER_BUFFER_M)),
                dict(c["dates"]) if c.get("dates") else None,
            )
    raise KeyError(f"unknown city_id {city_id!r} in {path or REGISTRY}")

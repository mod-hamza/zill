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

    @property
    def bbox_caster(self) -> dict[str, float]:
        return expand_bbox(self.bbox, config.CASTER_BUFFER_M)

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
            return CitySpec(c["city_id"], c["name"], c["bbox"], c["origin"], c["timezone"])
    raise KeyError(f"unknown city_id {city_id!r} in {path or REGISTRY}")

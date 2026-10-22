"""Synthetic scenes for tests and benchmarks (clearly not real data)."""

from __future__ import annotations

from typing import Any

import numpy as np

from zill.shade.heightmap import GridSpec


def box(bid: int, xa: float, za: float, xb: float, zb: float, h: float, min_h: float = 0.0,
        name: str | None = None) -> dict[str, Any]:
    return {"id": bid, "osm": f"synthetic/{bid}", "name": name, "height": float(h),
            "min_height": float(min_h),
            "source": "synthetic", "kind": "building", "in_scene": True,
            "footprint": [[xa, za], [xb, za], [xb, zb], [xa, zb]], "holes": []}


def square_grid(half_extent_m: float, res: float = 2.0) -> GridSpec:
    n = int(round(2 * half_extent_m / res))
    return GridSpec(-half_extent_m, -half_extent_m, n, n, res)


def random_city(n_boxes: int = 2500, half_extent_m: float = 1300.0, seed: int = 7,
                with_tower: bool = True) -> list[dict[str, Any]]:
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n_boxes):
        cx, cz = rng.uniform(-half_extent_m, half_extent_m, 2)
        w, d = rng.uniform(12, 60, 2)
        h = float(min(400.0, rng.lognormal(3.3, 0.8)))
        out.append(box(i, cx - w / 2, cz - d / 2, cx + w / 2, cz + d / 2, h))
    if with_tower:
        out.append(box(n_boxes, -30, -30, 30, 30, 828.0, name="Synthetic tower"))
    return out

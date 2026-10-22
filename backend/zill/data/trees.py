"""Trees (PRD 6.7): natural=tree nodes and natural=tree_row ways sampled every 6 m."""

from __future__ import annotations

from typing import Any

import numpy as np

from zill import config
from zill.data.heights import parse_length
from zill.geo import to_local


def elements_to_trees(
    elements: list[dict[str, Any]], origin: dict[str, float], clip_xz: tuple[float, float, float, float]
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    x0, z0, x1, z1 = clip_xz
    out: list[dict[str, Any]] = []
    stats = {"node": 0, "row_ways": 0, "row": 0, "crown_tagged": 0, "height_tagged": 0}

    def add(x: float, z: float, r: float, h: float, src: str) -> None:
        if x0 <= x <= x1 and z0 <= z <= z1:
            out.append({"x": round(x, 2), "z": round(z, 2), "r": round(r, 2), "h": round(h, 2), "src": src})
            stats[src] += 1

    for el in elements:
        tags = el.get("tags") or {}
        h_tag = parse_length(tags.get("height"))
        d_tag = parse_length(tags.get("diameter_crown"))
        r = d_tag / 2 if d_tag and 0.5 <= d_tag <= 40 else config.TREE_RADIUS_M
        h = h_tag if h_tag and 1.0 <= h_tag <= 60 else config.TREE_HEIGHT_M
        if el["type"] == "node" and tags.get("natural") == "tree":
            stats["crown_tagged"] += int(r != config.TREE_RADIUS_M)
            stats["height_tagged"] += int(h != config.TREE_HEIGHT_M)
            x, z = to_local(el["lat"], el["lon"], origin)
            add(float(x), float(z), r, h, "node")
        elif el["type"] == "way" and tags.get("natural") == "tree_row":
            g = [p for p in (el.get("geometry") or []) if p]
            if len(g) < 2:
                continue
            stats["row_ways"] += 1
            xs, zs = to_local(np.array([p["lat"] for p in g]), np.array([p["lon"] for p in g]), origin)
            pts = np.column_stack([xs, zs])
            seg = np.hypot(*np.diff(pts, axis=0).T)
            cum = np.concatenate([[0.0], np.cumsum(seg)])
            for s in np.arange(0.0, cum[-1] + 1e-6, config.TREE_ROW_SPACING_M):
                x = float(np.interp(s, cum, pts[:, 0]))
                z = float(np.interp(s, cum, pts[:, 1]))
                add(x, z, r, h, "row")
    out.sort(key=lambda t: (t["x"], t["z"]))
    return out, stats

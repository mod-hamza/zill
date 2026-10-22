"""Gazetteer resolution (PRD 6.2): curated hints resolved by name against OSM, plus extra named POIs."""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Any

from zill.geo import to_local

RESOLVE_RADIUS_M = 900.0
SNAP_WARN_M = 60.0

# per-kind caps keep the extra POI list varied (nearest to the city origin first)
AUTO_CAPS = {"hotel": 14, "mall": 5, "metro": 4, "park": 5, "landmark": 8, "cafe": 8}
AUTO_KINDS = [
    ("tourism", "hotel", "hotel"),
    ("shop", "mall", "mall"),
    ("railway", "station", "metro"),
    ("leisure", "park", "park"),
    ("tourism", "attraction", "landmark"),
    ("amenity", "theatre", "landmark"),
    ("tourism", "museum", "landmark"),
    ("amenity", "cafe", "cafe"),
]


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def _names(tags: dict[str, str]) -> list[str]:
    return [tags[k] for k in ("name:en", "name", "official_name", "alt_name", "brand") if tags.get(k)]


def _pos(el: dict[str, Any]) -> tuple[float, float] | None:
    if "lat" in el:
        return el["lat"], el["lon"]
    c = el.get("center")
    if c:
        return c["lat"], c["lon"]
    b = el.get("bounds")
    if b:
        return (b["minlat"] + b["maxlat"]) / 2, (b["minlon"] + b["maxlon"]) / 2
    return None


def _dist_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    dy = (a[0] - b[0]) * 110574.0
    dx = (a[1] - b[1]) * 111320.0 * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)


def resolve(
    gazetteer: list[dict[str, Any]], elements: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (pois, resolution_log). Unresolved entries fall back to the curated hint (source=curated)."""
    pois, rlog = [], []
    for g in gazetteer:
        hint = (g["hint"]["lat"], g["hint"]["lon"])
        matches = [m.lower() for m in g.get("match", [g["name"]])]
        prefer = g.get("prefer", {})
        best, best_score, best_d = None, math.inf, math.inf
        for el in elements:
            tags = el.get("tags") or {}
            names = [n.lower() for n in _names(tags)]
            if not names:
                continue
            exact = any(n == m for n in names for m in matches)
            partial = exact or any(m in n for n in names for m in matches)
            if not partial:
                continue
            if any(x.lower() in n for n in names for x in g.get("exclude", [])):
                continue
            p = _pos(el)
            if p is None:
                continue
            d = _dist_m(hint, p)
            if d > RESOLVE_RADIUS_M:
                continue
            score = (
                d + (0 if exact else 250) - (200 if any(tags.get(k) == v for k, v in prefer.items()) else 0)
            )
            if score < best_score:
                best, best_score, best_d = el, score, d
        if best is not None:
            p = _pos(best)
            assert p is not None
            name = g["name"]
            pois.append(
                {
                    "id": g["id"],
                    "name": name,
                    "lat": round(p[0], 7),
                    "lon": round(p[1], 7),
                    "kind": g["kind"],
                    "source": "osm",
                    "osm": f"{best['type']}/{best['id']}",
                    "osm_name": _names(best.get("tags") or {})[0],
                }
            )
            rlog.append(
                {
                    "id": g["id"],
                    "resolved": True,
                    "osm": f"{best['type']}/{best['id']}",
                    "lat": round(p[0], 7),
                    "lon": round(p[1], 7),
                    "hint_offset_m": round(best_d, 1),
                }
            )
        elif not g.get("required", True):
            rlog.append({"id": g["id"], "resolved": False, "dropped": True})
        else:
            pois.append(
                {
                    "id": g["id"],
                    "name": g["name"],
                    "lat": hint[0],
                    "lon": hint[1],
                    "kind": g["kind"],
                    "source": "curated",
                    "osm": None,
                    "verified": False,
                }
            )
            rlog.append({"id": g["id"], "resolved": False, "lat": hint[0], "lon": hint[1]})
    return pois, rlog


def auto_pois(
    elements: list[dict[str, Any]],
    core_bbox: dict[str, float],
    existing: list[dict[str, Any]],
    limit: int = 40,
    origin_ll: tuple[float, float] | None = None,
) -> list[dict[str, Any]]:
    """Extra real named POIs inside the core bbox (hotels, malls, stations, parks, attractions, cafes)."""
    seen_osm = {p.get("osm") for p in existing}
    seen_names = {p["name"].lower() for p in existing} | {
        str(p.get("osm_name", "")).lower() for p in existing
    }
    seen_ids = {p["id"] for p in existing}
    cands: list[tuple[int, float, str, dict[str, Any], str]] = []
    origin = ((core_bbox["s"] + core_bbox["n"]) / 2, (core_bbox["w"] + core_bbox["e"]) / 2)
    if origin_ll is not None:
        origin = origin_ll
    for el in elements:
        tags = el.get("tags") or {}
        names = _names(tags)
        if not names:
            continue
        kind = None
        rank = 99
        for r, (k, v, kd) in enumerate(AUTO_KINDS):
            if tags.get(k) == v:
                kind, rank = kd, r
                break
        if kind is None or (kind == "mall" and el["type"] == "node"):
            continue
        p = _pos(el)
        if p is None or not (
            core_bbox["s"] <= p[0] <= core_bbox["n"] and core_bbox["w"] <= p[1] <= core_bbox["e"]
        ):
            continue
        name = tags.get("name:en") or names[0]
        if not re.search(r"[A-Za-z]", name):
            continue
        cands.append((rank, _dist_m(origin, p), name, el, kind))
    cands.sort(key=lambda c: (c[0], c[1], c[2]))
    out = []
    per_kind: dict[str, int] = {}
    for _rank, _d, name, el, kind in cands:
        if per_kind.get(kind, 0) >= AUTO_CAPS.get(kind, 5):
            continue
        osm = f"{el['type']}/{el['id']}"
        pid = slug(name)
        if osm in seen_osm or name.lower() in seen_names or pid in seen_ids or not pid:
            continue
        p = _pos(el)
        assert p is not None
        out.append(
            {
                "id": pid,
                "name": name,
                "lat": round(p[0], 7),
                "lon": round(p[1], 7),
                "kind": kind,
                "source": "osm",
                "osm": osm,
            }
        )
        seen_osm.add(osm)
        seen_names.add(name.lower())
        seen_ids.add(pid)
        per_kind[kind] = per_kind.get(kind, 0) + 1
        if len(out) >= limit:
            break
    return out


def project(pois: list[dict[str, Any]], origin: dict[str, float]) -> None:
    for p in pois:
        x, z = to_local(p["lat"], p["lon"], origin)
        p["x"] = round(float(x), 2)
        p["z"] = round(float(z), 2)

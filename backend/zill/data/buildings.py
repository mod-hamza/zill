"""OSM building/part elements -> projected, cleaned footprints with heights (PRD 6.4, 6.8)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import shapely
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import polygonize, unary_union

from zill.data.heights import building_height
from zill.geo import to_local

log = logging.getLogger("zill.data.buildings")

MIN_AREA_M2 = 4.0
SIMPLIFY_M = 0.3


@dataclass
class Building:
    osm: str
    tags: dict[str, str]
    kind: str  # building|part
    poly: Polygon
    height: float = 0.0
    min_height: float = 0.0
    source: str = "fallback"
    name: str | None = None
    in_scene: bool = False
    id: int = -1
    extra: dict[str, Any] = field(default_factory=dict)


def _ring_xy(geom: list[dict[str, float]], origin: dict[str, float]) -> np.ndarray:
    lat = np.array([p["lat"] for p in geom], dtype=float)
    lon = np.array([p["lon"] for p in geom], dtype=float)
    x, z = to_local(lat, lon, origin)
    return np.column_stack([x, z])


def _clean(geom: Any) -> list[Polygon]:
    if geom is None or geom.is_empty:
        return []
    if not geom.is_valid:
        geom = shapely.make_valid(geom)
        if not isinstance(geom, Polygon | MultiPolygon):
            geom = unary_union(
                [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon | MultiPolygon)]
            )
        if not geom.is_valid:
            geom = geom.buffer(0)
    out: list[Polygon] = []
    for p in getattr(geom, "geoms", [geom]):
        if not isinstance(p, Polygon) or p.is_empty or p.area < MIN_AREA_M2:
            continue
        s = p.simplify(SIMPLIFY_M, preserve_topology=True)
        if isinstance(s, Polygon) and s.is_valid and s.area >= MIN_AREA_M2:
            out.append(s)
        elif s.area >= MIN_AREA_M2:
            out.extend(q for q in getattr(s, "geoms", []) if isinstance(q, Polygon) and q.area >= MIN_AREA_M2)
    return out


def _way_polys(el: dict[str, Any], origin: dict[str, float]) -> list[Polygon]:
    g = el.get("geometry") or []
    if len(g) < 4:
        return []
    xy = _ring_xy(g, origin)
    return _clean(Polygon(xy))


def _rel_polys(el: dict[str, Any], origin: dict[str, float], outer_roles: tuple[str, ...]) -> list[Polygon]:
    outers, inners = [], []
    for m in el.get("members", []):
        if m.get("type") != "way" or not m.get("geometry"):
            continue
        g = [p for p in m["geometry"] if p]  # members may contain nulls outside bbox
        if len(g) < 2:
            continue
        line = shapely.LineString(_ring_xy(g, origin))
        role = m.get("role") or "outer"
        (inners if role == "inner" else outers if role in outer_roles else []).append(line)
    if not outers:
        return []
    outer_polys = list(polygonize(unary_union(outers)))
    if not outer_polys:
        return []
    geom = unary_union(outer_polys)
    if inners:
        inner_polys = list(polygonize(unary_union(inners)))
        if inner_polys:
            geom = geom.difference(unary_union(inner_polys))
    return _clean(geom)


def elements_to_buildings(elements: list[dict[str, Any]], origin: dict[str, float]) -> list[Building]:
    """Parse ways and relations tagged building / building:part into Building records (unfiltered)."""
    out: list[Building] = []
    for el in elements:
        tags = el.get("tags") or {}
        is_part = "building:part" in tags and tags.get("building:part") != "no"
        is_bldg = "building" in tags and tags.get("building") != "no"
        if not (is_part or is_bldg):
            continue
        kind = "part" if is_part else "building"
        osm = f"{el['type']}/{el['id']}"
        if el["type"] == "way":
            polys = _way_polys(el, origin)
        elif el["type"] == "relation":
            rtype = tags.get("type")
            if rtype == "multipolygon":
                polys = _rel_polys(el, origin, ("outer", ""))
            elif rtype == "building":
                polys = _rel_polys(el, origin, ("outline",))
            else:
                polys = []
        else:
            polys = []
        for i, p in enumerate(polys):
            b = Building(osm=osm if len(polys) == 1 else f"{osm}#{i}", tags=tags, kind=kind, poly=p)
            b.name = tags.get("name:en") or tags.get("name")
            b.height, b.min_height, b.source = building_height(tags)
            out.append(b)
    return out


SHELL_COVER_MIN = 0.5


def drop_shells_with_parts(blds: list[Building]) -> tuple[list[Building], int]:
    """Parts replace their shell (PRD 6.4 rule 1).

    A shell "has parts" when >=1 building:part polygon has its centroid inside it. If the parts cover
    >= ``SHELL_COVER_MIN`` of the shell area the shell is dropped (classic Simple-3D-Buildings case,
    e.g. Burj Khalifa). If they cover less (e.g. The Dubai Mall: one 3.8 ha car-park part inside a
    24.6 ha shell), dropping the shell would delete most of the building, so the shell is kept minus
    the parts' footprint (no double counting, no overlap). The shell's name passes to its tallest part
    when the shell is dropped. Returns (buildings, n_shells_dropped); partial count in ``PARTIAL``.
    """
    parts = [b for b in blds if b.kind == "part"]
    shells = [b for b in blds if b.kind == "building"]
    PARTIAL.clear()
    if not parts:
        return blds, 0
    cents = shapely.points([p.poly.centroid.coords[0] for p in parts])
    tree = shapely.STRtree(cents)
    drop: set[int] = set()
    extra: list[Building] = []
    for si, s in enumerate(shells):
        idx = tree.query(s.poly, predicate="contains")
        if not len(idx):
            continue
        drop.add(si)
        inside = [parts[i] for i in idx]
        union = unary_union([p.poly for p in inside])
        cover = union.intersection(s.poly).area / max(s.poly.area, 1e-9)
        for p in inside:
            p.extra["shell_height"] = s.height
            p.extra["shell_source"] = s.source
        if cover >= SHELL_COVER_MIN:
            tallest = max(inside, key=lambda p: p.height)
            tallest.extra.setdefault("shell_osm", s.osm)
            if s.name and not tallest.name:
                tallest.name = s.name
            continue
        rest = _clean(s.poly.difference(union))
        PARTIAL.append(s.osm)
        for k, poly in enumerate(rest):
            b = Building(
                osm=s.osm if len(rest) == 1 else f"{s.osm}#r{k}", tags=s.tags, kind="building", poly=poly
            )
            b.name, b.height, b.min_height, b.source = s.name, s.height, s.min_height, s.source
            b.extra["parts_cover"] = round(cover, 3)
            extra.append(b)
    kept = [s for i, s in enumerate(shells) if i not in drop] + extra + parts
    return kept, len(drop) - len(PARTIAL)


PARTIAL: list[str] = []


def apply_landmarks(blds: list[Building], landmarks: list[dict[str, Any]]) -> int:
    """Curated overrides always win. Entries: {osm?: 'way/1', name?: str, height: m, min_height?: m}."""
    n = 0
    for lm in landmarks:
        for b in blds:
            base_osm = b.osm.split("#")[0]
            hit = (lm.get("osm") and base_osm == lm["osm"]) or (
                not lm.get("osm")
                and lm.get("name")
                and b.name == lm["name"]
                and b.kind == lm.get("kind", b.kind)
            )
            if hit:
                if lm.get("set_name"):
                    b.name = lm["set_name"]
                if "height" in lm:
                    b.height = float(lm["height"])
                    if "min_height" in lm:
                        b.min_height = float(lm["min_height"])
                    b.source = "landmark"
                    n += 1
    return n


def finalize(
    blds: list[Building],
    caster_xz: tuple[float, float, float, float],
    scene_xz: tuple[float, float, float, float],
) -> list[Building]:
    """Keep buildings whose representative point is inside the caster box; flag in_scene; assign ids."""
    x0, z0, x1, z1 = caster_xz
    sx0, sz0, sx1, sz1 = scene_xz
    kept = []
    for b in blds:
        p = b.poly.representative_point()
        if not (x0 <= p.x <= x1 and z0 <= p.y <= z1):
            continue
        b.in_scene = sx0 <= p.x <= sx1 and sz0 <= p.y <= sz1
        kept.append(b)
    kept.sort(key=lambda b: (b.osm.split("/")[0], int(b.osm.split("/")[1].split("#")[0]), b.osm))
    for i, b in enumerate(kept):
        b.id = i
    return kept


def _ring(coords: Any) -> list[list[float]]:
    pts = list(coords)[:-1]  # rings not closed
    return [[round(float(x), 2), round(float(z), 2)] for x, z in pts]


def to_json(b: Building) -> dict[str, Any]:
    return {
        "id": b.id,
        "osm": b.osm,
        "name": b.name,
        "height": round(b.height, 2),
        "min_height": round(b.min_height, 2),
        "source": b.source if b.kind == "building" or b.source == "landmark" else "part",
        "height_rule": b.source,
        "kind": b.kind,
        "in_scene": b.in_scene,
        "footprint": _ring(b.poly.exterior.coords),
        "holes": [_ring(r.coords) for r in b.poly.interiors],
    }

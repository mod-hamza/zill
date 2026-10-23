"""City bake (PRD 6): ``python -m zill.data.bake --city dubai_downtown [--refresh]``.

City-agnostic: config comes only from ``data/cities.json`` ({city_id, name, bbox, origin, timezone}).
Optional per-city curated overrides live in ``data/curated/<city_id>/`` (landmarks.json,
ac_links.geojson, entrances.json, gazetteer.json).

Shade stream hook: functions appended to ``POST_BAKE_HOOKS`` are called after the write step with
``(spec, out_dir, meta)``; they may append to ``meta["build_log"]`` (meta.json is rewritten after).
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import time
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import shapely
from scipy.spatial import cKDTree

from zill import config
from zill.data import overpass
from zill.data.buildings import (
    PARTIAL,
    apply_landmarks,
    drop_shells_with_parts,
    elements_to_buildings,
    finalize,
    to_json,
)
from zill.data.cities import CitySpec, get_city_spec
from zill.data.glb import verify_glb, write_glb
from zill.data.graph import (
    Edge,
    GraphBuild,
    build_graph,
    enforce_entrances,
    largest_components,
    link_entrances,
    to_columnar,
)
from zill.data.pois import SNAP_WARN_M, auto_pois, project, resolve
from zill.data.trees import elements_to_trees
from zill.geo import to_local, to_wgs84

log = logging.getLogger("zill.data.bake")

CURATED_DIR = config.DATA_DIR / "curated"
POST_BAKE_HOOKS: list[Callable[[CitySpec, Path, dict[str, Any]], None]] = []


def bbox_xz(b: dict[str, float], origin: dict[str, float]) -> tuple[float, float, float, float]:
    """WGS84 bbox -> local (xmin, zmin, xmax, zmax)."""
    xw, zn = to_local(b["n"], b["w"], origin)
    xe, zs = to_local(b["s"], b["e"], origin)
    return float(xw), float(zn), float(xe), float(zs)


def grid_spec(xz: tuple[float, float, float, float], res: float = config.GRID_RES_M) -> dict[str, Any]:
    x0 = math.floor(xz[0] / res) * res
    z0 = math.floor(xz[1] / res) * res
    cols = int(math.ceil((xz[2] - x0) / res))
    rows = int(math.ceil((xz[3] - z0) / res))
    return {"x0": x0, "z0": z0, "rows": rows, "cols": cols, "res_m": res}


def _load_curated(city_id: str, name: str) -> Any:
    p = CURATED_DIR / city_id / name
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _dump(path: Path, obj: Any, indent: int | None = None) -> None:
    path.write_text(
        json.dumps(obj, indent=indent, separators=None if indent else (",", ":"), ensure_ascii=False),
        encoding="utf-8",
    )


class StepLog:
    def __init__(self) -> None:
        self.t0 = time.perf_counter()
        self.entries: list[dict[str, Any]] = []
        self._start = 0.0

    def start(self) -> None:
        self._start = time.perf_counter()

    def done(self, step: str, count: int, label: str) -> None:
        now = time.perf_counter()
        self.entries.append(
            {
                "t_ms": int((self._start - self.t0) * 1000),
                "dur_ms": int((now - self._start) * 1000),
                "step": step,
                "count": int(count),
                "label": label,
            }
        )
        log.info("%-16s %8d  %s  (%.1fs)", step, count, label, now - self._start)


def apply_curated_links(gb: GraphBuild, feats: list[dict[str, Any]], origin: dict[str, float]) -> list[dict]:
    """Curated ac_links: reclassify listed OSM ways, or insert a new edge between nearest graph nodes."""
    report = []
    walk_nodes = sorted({n for e in gb.edges if e.walk for n in (e.u, e.v)})
    pts = np.array([gb.nodes[n][:2] for n in walk_nodes]) if walk_nodes else np.zeros((0, 2))
    tree = cKDTree(pts) if len(pts) else None
    for f in feats:
        props = f.get("properties") or {}
        cls = props.get("cls", "ac_link")
        verified = bool(props.get("verified", False))
        name = props.get("name")
        osm_ways = set(props.get("osm_ways") or [])
        if osm_ways:
            n = 0
            for e in gb.edges:
                if e.osm in osm_ways:
                    e.cls, e.curated, e.verified = cls, True, verified
                    n += 1
            report.append({"name": name, "mode": "reclassify", "edges": n, "verified": verified})
            continue
        coords = f["geometry"]["coordinates"]
        lon = np.array([c[0] for c in coords])
        lat = np.array([c[1] for c in coords])
        xs, zs = to_local(lat, lon, origin)
        line = list(zip(xs.tolist(), zs.tolist(), strict=True))
        if tree is None:
            continue
        du, iu = tree.query(line[0])
        dv, iv = tree.query(line[-1])
        u, v = walk_nodes[int(iu)], walk_nodes[int(iv)]
        max_snap = float(props.get("max_snap_m", 40.0))
        if du > max_snap or dv > max_snap or u == v:
            report.append(
                {
                    "name": name,
                    "mode": "insert",
                    "edges": 0,
                    "snap_m": [round(du, 1), round(dv, 1)],
                    "skipped": True,
                }
            )
            continue
        geom = [gb.nodes[u][:2], *line[1:-1], gb.nodes[v][:2]]
        tags = {"highway": props.get("highway", "footway"), "name": name or ""}
        e = Edge(
            u,
            v,
            [tuple(p) for p in geom],
            tags,
            props.get("osm", "curated"),
            True,
            False,
            cls=cls,
            curated=True,
            verified=verified,
            name=name,
        )
        gb.edges.append(e)
        report.append(
            {
                "name": name,
                "mode": "insert",
                "edges": 1,
                "snap_m": [round(du, 1), round(dv, 1)],
                "length_m": round(e.length, 1),
                "verified": verified,
            }
        )
    return report


def apply_curated_entrances(gb: GraphBuild, ents: list[dict[str, Any]], origin: dict[str, float]) -> int:
    nodes = sorted({n for e in gb.edges for n in (e.u, e.v)})
    if not nodes:
        return 0
    tree = cKDTree(np.array([gb.nodes[n][:2] for n in nodes]))
    n = 0
    for en in ents:
        x, z = to_local(en["lat"], en["lon"], origin)
        d, i = tree.query((float(x), float(z)))
        if d <= float(en.get("max_snap_m", 15.0)):
            gb.curated_entrance.add(nodes[int(i)])
            n += 1
    return n


def links_geojson(graph: dict[str, Any], origin: dict[str, float]) -> dict[str, Any]:
    feats = []
    E = graph["edges"]
    for i, cls in enumerate(E["cls"]):
        if cls == "open":
            continue
        g = np.array(E["geom"][i]).reshape(-1, 2)
        lat, lon = to_wgs84(g[:, 0], g[:, 1], origin)
        feats.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [round(float(a), 7), round(float(b), 7)] for a, b in zip(lon, lat, strict=True)
                    ],
                },
                "properties": {
                    "edge": i,
                    "cls": cls,
                    "name": E["name"][i],
                    "verified": E["verified"][i],
                    "curated": E["curated"][i],
                    "osm": E["osm"][i],
                },
            }
        )
    return {"type": "FeatureCollection", "features": feats}


def snap_pois(
    pois: list[dict[str, Any]], graph: dict[str, Any], footprints: dict[str, Any] | None = None
) -> list[str]:
    """Snap each POI to its nearest walk node. If that node is outdoor-only and the POI's own OSM building
    has a mapped entrance (graph entrance node within 10 m of its outline, <= 150 m from the POI), snap to
    that door instead: you enter the Burj Khalifa through its door, not from the nearest lawn path."""
    N, E = graph["nodes"], graph["edges"]
    walk_nodes = sorted({n for i, w in enumerate(E["walk"]) if w for n in (E["u"][i], E["v"][i])})
    xy = np.column_stack([np.array(N["x"])[walk_nodes], np.array(N["z"])[walk_nodes]])
    tree = cKDTree(xy)
    inside_nodes = {
        n for i, w in enumerate(E["walk"]) if w and E["cls"][i] != "open" for n in (E["u"][i], E["v"][i])
    }
    ent = [n for n in walk_nodes if N["entrance"][n]]
    ent_pts = shapely.points(np.column_stack([np.array(N["x"])[ent], np.array(N["z"])[ent]])) if ent else None
    warns = []
    for p in pois:
        d, i = tree.query((p["x"], p["z"]))
        node, snap = int(walk_nodes[int(i)]), "nearest"
        fp = (footprints or {}).get(p.get("osm") or "")
        if fp is not None and node not in inside_nodes and ent_pts is not None:
            near = [
                k
                for k in range(len(ent))
                if fp.exterior.distance(ent_pts[k]) <= 10.0 or fp.contains(ent_pts[k])
            ]
            if near:
                k = min(near, key=lambda k: (N["x"][ent[k]] - p["x"]) ** 2 + (N["z"][ent[k]] - p["z"]) ** 2)
                de = float(np.hypot(N["x"][ent[k]] - p["x"], N["z"][ent[k]] - p["z"]))
                if de <= 150.0:
                    node, d, snap = ent[k], de, "entrance"
        p["node"] = node
        p["snap_m"] = round(float(d), 1)
        p["snap"] = snap
        if d > SNAP_WARN_M:
            warns.append(f"{p['id']} snapped {d:.0f} m ({snap})")
    return warns


def bake(city_id: str, refresh: bool = False, out_root: Path | None = None, run_hooks: bool = True) -> dict:
    spec = get_city_spec(city_id)
    origin = spec.origin
    out = (out_root or config.CITIES_DIR) / city_id
    out.mkdir(parents=True, exist_ok=True)
    sl = StepLog()
    overpass.STATS.__init__()

    # 1. geocode: bboxes, grids, gazetteer elements
    sl.start()
    scene_xz = bbox_xz(spec.bbox_scene, origin)
    caster_xz = bbox_xz(spec.bbox_caster, origin)
    poi_els = overpass.fetch_pois(spec.bbox_scene, city_id, refresh=refresh)
    gaz = _load_curated(city_id, "gazetteer.json") or []
    pois, poi_log = resolve(gaz, poi_els)
    pois += auto_pois(poi_els, spec.bbox, pois, origin_ll=(origin["lat"], origin["lon"]))
    project(pois, origin)
    sl.done(
        "geocode",
        len(pois),
        f"{len(pois)} places resolved ({sum(r['resolved'] for r in poi_log)}/{len(poi_log)} gazetteer hits)",
    )

    # 2. buildings
    sl.start()
    b_els = overpass.fetch_buildings(spec.bbox_caster, city_id, refresh=refresh)
    sl.done("fetch_buildings", len(b_els), f"{len(b_els)} OSM building elements")

    # 3. roads
    sl.start()
    r_els = overpass.fetch_roads(spec.bbox_scene, city_id, refresh=refresh)
    n_ways = sum(1 for e in r_els if e["type"] == "way")
    sl.done("fetch_roads", n_ways, f"{n_ways} OSM ways (highway/indoor)")

    # 4. trees
    sl.start()
    t_els = overpass.fetch_trees(spec.bbox_caster, city_id, refresh=refresh)
    trees, tree_stats = elements_to_trees(t_els, origin, caster_xz)
    sl.done(
        "fetch_trees",
        len(trees),
        f"{len(trees)} trees ({tree_stats['node']} mapped, {tree_stats['row']} from rows)",
    )

    # 5. heights
    sl.start()
    raw_blds = elements_to_buildings(b_els, origin)
    indoor_polys = [b.poly for b in raw_blds if b.min_height < 3.0]
    shell_polys = [b.poly for b in raw_blds if b.kind == "building"]
    blds, n_shell_drop = drop_shells_with_parts(raw_blds)
    landmarks = _load_curated(city_id, "landmarks.json") or []
    n_land = apply_landmarks(blds, landmarks)
    blds = finalize(blds, caster_xz, scene_xz)
    bjson = [to_json(b) for b in blds]
    hs = Counter(b["source"] for b in bjson)
    height_sources = {k: hs.get(k, 0) for k in ("tag", "levels", "fallback", "landmark", "part")}
    max_h = max((b["height"] for b in bjson), default=0.0)
    sl.done(
        "heights",
        len(bjson),
        f"{len(bjson)} footprints; max {max_h:.0f} m; {n_shell_drop} shells replaced by parts",
    )

    # 6. graph
    sl.start()
    gb = build_graph(r_els, origin, indoor_polys, scene_xz)
    sl.done("graph", len(gb.edges), f"{len(gb.edges)} raw edges split at intersections")

    # 7. covered / indoor / ac links
    sl.start()
    ac_feats = (_load_curated(city_id, "ac_links.geojson") or {}).get("features", [])
    link_report = apply_curated_links(gb, ac_feats, origin)
    ents = _load_curated(city_id, "entrances.json") or []
    n_cur_ent = apply_curated_entrances(gb, ents, origin)
    ent_links = link_entrances(gb, shell_polys)
    enforce_entrances(gb, shell_polys)
    dropped = largest_components(gb)
    graph, _remap = to_columnar(gb)
    E = graph["edges"]
    cls_count = Counter(E["cls"])
    links = links_geojson(graph, origin)
    sl.done(
        "covered_links",
        len(links["features"]),
        f"{cls_count.get('covered', 0)} covered, {cls_count.get('indoor', 0)} indoor, "
        f"{cls_count.get('ac_link', 0)} AC-link edges",
    )

    # 8. write
    sl.start()
    poi_warns = snap_pois(pois, graph, {b.osm: b.poly for b in raw_blds})
    glb_report = write_glb(blds, out / "buildings.glb", (scene_xz[0], scene_xz[1]))
    glb_report["verify"] = verify_glb(out / "buildings.glb")
    _dump(out / "buildings.json", {"buildings": bjson})
    _dump(out / "trees.json", {"trees": trees})
    _dump(out / "graph.json", graph)
    _dump(out / "links.geojson", links)
    _dump(out / "pois.json", {"pois": pois}, indent=1)
    _dump(out / "glb_report.json", glb_report, indent=1)
    n_edges = len(E["u"])
    meta: dict[str, Any] = {
        "city_id": city_id,
        "name": spec.name,
        "timezone": spec.timezone,
        "origin": origin,
        "bbox_core": spec.bbox,
        "bbox_caster": spec.bbox_caster,
        "bbox_scene": spec.bbox_scene,
        "core_grid": grid_spec(
            bbox_xz(
                {
                    "s": spec.bbox_scene["s"],
                    "w": spec.bbox_scene["w"],
                    "n": spec.bbox_scene["n"],
                    "e": spec.bbox_scene["e"],
                },
                origin,
            )
        ),
        "caster_grid": grid_spec(caster_xz),
        "counts": {
            "buildings": len(bjson),
            "buildings_scene": sum(b["in_scene"] for b in bjson),
            "building_parts": sum(b["kind"] == "part" for b in bjson),
            "trees": len(trees),
            "nodes": len(graph["nodes"]["x"]),
            "edges": n_edges,
            "edges_walk": sum(E["walk"]),
            "edges_cycle": sum(E["cycle"]),
            "covered_edges": cls_count.get("covered", 0),
            "indoor_edges": cls_count.get("indoor", 0),
            "ac_link_edges": cls_count.get("ac_link", 0),
            "pois": len(pois),
        },
        "height_sources": height_sources,
        "dropped_components": dropped,
        "max_building_height_m": round(max_h, 2),
        "source": {
            "osm_timestamp": overpass.STATS.osm_timestamp,
            "fetched_at": datetime.now(UTC).isoformat(),
            "overpass_endpoint": overpass.STATS.endpoint,
        },
        "attribution": "© OpenStreetMap contributors",
        "dates": dict(config.PRESET_DATES),
        "build_log": sl.entries,
        "diagnostics": {
            "shells_replaced_by_parts": n_shell_drop,
            "shells_kept_partial_parts": list(PARTIAL),
            "landmark_overrides": n_land,
            "tree_stats": tree_stats,
            "graph_log": gb.log,
            "curated_links": link_report,
            "curated_entrances_snapped": n_cur_ent,
            "entrance_links": ent_links,
            "poi_resolution": poi_log,
            "poi_snap_warnings": poi_warns,
            "overpass_requests": overpass.STATS.requests,
            "overpass_cache_hits": overpass.STATS.cache_hits,
            "glb": {k: v for k, v in glb_report.items() if k != "tile_list"},
        },
    }
    sl.done("write", 7, "meta, buildings(.json/.glb), trees, graph, links, pois")
    meta["build_log"] = sl.entries
    _dump(out / "meta.json", meta, indent=1)
    if run_hooks:
        for hook in POST_BAKE_HOOKS:
            hook(spec, out, meta)
        if POST_BAKE_HOOKS:
            _dump(out / "meta.json", meta, indent=1)
    meta["_wall_s"] = round(time.perf_counter() - sl.t0, 2)
    return meta


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Bake a city from OSM")
    ap.add_argument("--city", default=config.DEFAULT_CITY)
    ap.add_argument("--refresh", action="store_true", help="ignore the raw Overpass cache")
    ap.add_argument("--no-hooks", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    meta = bake(a.city, refresh=a.refresh, run_hooks=not a.no_hooks)
    print(
        json.dumps(
            {
                "counts": meta["counts"],
                "height_sources": meta["height_sources"],
                "max_building_height_m": meta["max_building_height_m"],
                "wall_s": meta["_wall_s"],
            }
        )
    )


if __name__ == "__main__":
    main()

"""Walkable / cyclable graph from OSM highway ways (PRD 6.5) + link classification (PRD 6.6)."""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon

from zill.geo import to_local

log = logging.getLogger("zill.data.graph")

WALK_CLASSES = {
    "footway",
    "pedestrian",
    "path",
    "steps",
    "living_street",
    "residential",
    "service",
    "tertiary",
    "tertiary_link",
    "secondary",
    "secondary_link",
    "primary",
    "primary_link",
    "cycleway",
    "track",
    "unclassified",
    "corridor",
    "road",
    "bridleway",
}
ROAD_CYCLE_CLASSES = {
    "residential",
    "service",
    "tertiary",
    "tertiary_link",
    "secondary",
    "secondary_link",
    "primary",
    "primary_link",
    "unclassified",
    "living_street",
    "track",
    "road",
}
PED_ONLY = {"footway", "pedestrian", "path", "steps", "corridor", "bridleway"}
INDOOR_HW = {"footway", "corridor", "pedestrian", "path"}
YES = {"yes", "designated", "permissive", "official", "destination"}
NO = {"no", "private", "use_sidepath"}
PRIVATE_ACCESS = {"no", "private", "customers_only"}


@dataclass
class Edge:
    u: int  # osm node id (before reindex)
    v: int
    geom: list[tuple[float, float]]
    tags: dict[str, str]
    osm: str
    walk: bool
    cycle: bool
    cls: str = "open"
    curated: bool = False
    verified: bool = True
    name: str | None = None

    @property
    def length(self) -> float:
        g = np.asarray(self.geom)
        return float(np.sum(np.hypot(*(np.diff(g, axis=0).T))))


@dataclass
class GraphBuild:
    nodes: dict[int, tuple[float, float, float, float]] = field(default_factory=dict)  # id -> x,z,lat,lon
    edges: list[Edge] = field(default_factory=list)
    entrance: set[int] = field(default_factory=set)
    curated_entrance: set[int] = field(default_factory=set)
    crossing: set[int] = field(default_factory=set)
    free_entrance: dict[int, tuple[float, float, float, float]] = field(default_factory=dict)  # not on a way
    log: dict[str, Any] = field(default_factory=dict)


def mode_flags(tags: dict[str, str]) -> tuple[bool, bool]:
    hw = tags.get("highway", "")
    if hw not in WALK_CLASSES:
        return False, False
    if tags.get("area") == "yes" and hw != "pedestrian":
        return False, False
    access = tags.get("access", "")
    foot = tags.get("foot", "")
    bicycle = tags.get("bicycle", "")
    private = access in PRIVATE_ACCESS or (hw == "service" and tags.get("service") == "private")
    walk = True
    if foot in NO or (private and foot not in YES):
        walk = False
    cycle = False
    if hw == "cycleway" or hw in ROAD_CYCLE_CLASSES:
        cycle = bicycle not in NO
    elif hw in PED_ONLY and hw not in ("steps", "corridor"):
        cycle = bicycle in ("yes", "designated")
    if private and bicycle not in YES:
        cycle = False
    return walk, cycle


def _is_elevated(tags: dict[str, str]) -> bool:
    """Bridge-like: bridge=* or a positive layer outside buildings. (level=* alone = upper mall floor.)"""
    try:
        layer = float(tags.get("layer", "0").split(";")[0])
    except ValueError:
        layer = 0.0
    if tags.get("bridge", "no") not in ("no", ""):
        return True
    return layer > 0 and tags.get("highway") != "corridor" and tags.get("indoor", "no") in ("no", "")


def classify_tags(tags: dict[str, str]) -> str | None:
    """Tag-based class: ac_link / covered / indoor, or None (geometry test decides later)."""
    covered = tags.get("covered", "no")
    indoor = tags.get("indoor", "no")
    hw = tags.get("highway", "")
    enclosed = indoor not in ("no", "") or hw == "corridor"
    if _is_elevated(tags) and (enclosed or covered in ("yes",)) and hw in INDOOR_HW | {"steps"}:
        return "ac_link"
    if covered in ("yes", "arcade", "colonnade") or tags.get("tunnel") == "building_passage":
        return "covered"
    if enclosed:
        return "indoor"
    return None


def build_graph(
    elements: list[dict[str, Any]],
    origin: dict[str, float],
    indoor_polys: list[Polygon],
    clip_xz: tuple[float, float, float, float],
) -> GraphBuild:
    gb = GraphBuild()
    node_tags: dict[int, dict[str, str]] = {}
    node_ll: dict[int, tuple[float, float]] = {}
    ways = []
    for el in elements:
        if el["type"] == "node":
            node_tags[el["id"]] = el.get("tags") or {}
            node_ll[el["id"]] = (el["lat"], el["lon"])
        elif el["type"] == "way" and "highway" in (el.get("tags") or {}):
            ways.append(el)
    # coordinates for all way nodes
    coords: dict[int, tuple[float, float]] = {}
    kept_ways = []
    for w in ways:
        tags = w.get("tags") or {}
        walk, cycle = mode_flags(tags)
        if not (walk or cycle):
            continue
        geom = w.get("geometry") or []
        nids = w.get("nodes") or []
        if len(geom) != len(nids) or len(nids) < 2 or any(p is None for p in geom):
            continue
        for nid, p in zip(nids, geom, strict=True):
            coords[nid] = (p["lat"], p["lon"])
        kept_ways.append((w, tags, walk, cycle))
    use = defaultdict(int)
    for w, _t, _a, _b in kept_ways:
        nids = w["nodes"]
        for i, n in enumerate(nids):
            use[n] += 2 if i in (0, len(nids) - 1) else 1
    split_extra = {
        n
        for n, t in node_tags.items()
        if t.get("highway") in ("crossing", "elevator")
        or "crossing" in t
        or "entrance" in t
        or t.get("railway") == "subway_entrance"
    }
    ids = np.array(list(coords.keys()), dtype=np.int64)
    lat = np.array([coords[i][0] for i in ids])
    lon = np.array([coords[i][1] for i in ids])
    xs, zs = to_local(lat, lon, origin)
    xz = {int(i): (float(x), float(z)) for i, x, z in zip(ids, xs, zs, strict=True)}
    for w, tags, walk, cycle in kept_ways:
        nids = w["nodes"]
        start = 0
        for i in range(1, len(nids)):
            n = nids[i]
            if i == len(nids) - 1 or use[n] >= 2 or n in split_extra:
                seg = nids[start : i + 1]
                segs = [seg]
                if seg[0] == seg[-1] and len(seg) >= 3:  # closed loop: split in two
                    m = len(seg) // 2
                    segs = [seg[: m + 1], seg[m:]]
                for sg in segs:
                    geom = [xz[k] for k in sg]
                    e = Edge(
                        sg[0],
                        sg[-1],
                        geom,
                        tags,
                        f"way/{w['id']}",
                        walk,
                        cycle,
                        name=tags.get("name:en") or tags.get("name"),
                    )
                    if e.u != e.v and e.length > 0.05:
                        gb.edges.append(e)
                start = i
    for n in coords:
        gb.nodes[n] = (xz[n][0], xz[n][1], coords[n][0], coords[n][1])
    for n, t in node_tags.items():
        if n not in gb.nodes:
            if "entrance" in t and t.get("entrance") != "no" and n in node_ll:
                la, lo = node_ll[n]
                fx, fz = to_local(la, lo, origin)
                gb.free_entrance[n] = (float(fx), float(fz), la, lo)
            continue
        if "entrance" in t or t.get("railway") == "subway_entrance" or t.get("door") not in (None, "no"):
            gb.entrance.add(n)
        if (
            t.get("highway") == "crossing"
            or t.get("railway") == "crossing"
            or ("crossing" in t and t.get("crossing") != "no")
        ):
            gb.crossing.add(n)
    _crossing_ways(gb)
    _clip(gb, clip_xz)
    classify_edges(gb, indoor_polys)
    return gb


def _crossing_ways(gb: GraphBuild) -> None:
    """footway=crossing ways without a tagged crossing node: flag their node shared with a road."""
    by_node: dict[int, list[Edge]] = defaultdict(list)
    for e in gb.edges:
        by_node[e.u].append(e)
        by_node[e.v].append(e)
    n_added = 0
    cross_ways: dict[str, list[Edge]] = defaultdict(list)
    for e in gb.edges:
        if e.tags.get("footway") == "crossing" or e.tags.get("cycleway") == "crossing":
            cross_ways[e.osm].append(e)
    for _osm, es in cross_ways.items():
        nodes = {n for e in es for n in (e.u, e.v)}
        if nodes & gb.crossing:
            continue
        road_nodes = [n for n in nodes if any(x.tags.get("highway") not in PED_ONLY for x in by_node[n])]
        pick = sorted(road_nodes)[0] if road_nodes else min(nodes)
        gb.crossing.add(pick)
        n_added += 1
    gb.log["crossing_from_ways"] = n_added


def _clip(gb: GraphBuild, clip_xz: tuple[float, float, float, float]) -> None:
    """Keep only edges whose both endpoints are inside the scene box."""
    x0, z0, x1, z1 = clip_xz

    def inside(n: int) -> bool:
        x, z = gb.nodes[n][:2]
        return x0 <= x <= x1 and z0 <= z <= z1

    before = len(gb.edges)
    gb.edges = [e for e in gb.edges if inside(e.u) and inside(e.v)]
    gb.log["clipped_edges"] = before - len(gb.edges)


def classify_edges(gb: GraphBuild, indoor_polys: list[Polygon]) -> None:
    tree = shapely.STRtree(indoor_polys) if indoor_polys else None
    counts: dict[str, int] = defaultdict(int)
    for e in gb.edges:
        c = classify_tags(e.tags)
        if c is None and tree is not None and e.tags.get("highway") in INDOOR_HW:
            mid = LineString(e.geom).interpolate(0.5, normalized=True)
            if len(tree.query(mid, predicate="within")) and e.tags.get("covered") != "no":
                c = "indoor"
        e.cls = c or "open"
        counts[e.cls] += 1
    gb.log["cls_counts"] = dict(counts)


def enforce_entrances(gb: GraphBuild, building_polys: list[Polygon], door_tol_m: float = 3.0) -> None:
    """Outdoor<->indoor transitions only at entrance nodes (PRD 6.6).

    A non-entrance transition node is split (indoor edges get a new node id) unless it lies within
    ``door_tol_m`` of a building wall, in which case it is accepted as a curated entrance (logged).
    """
    inside_cls = {"indoor", "ac_link"}
    inc: dict[int, list[Edge]] = defaultdict(list)
    for e in gb.edges:
        inc[e.u].append(e)
        inc[e.v].append(e)
    walls = shapely.STRtree([p.exterior for p in building_polys]) if building_polys else None
    next_id = -1
    n_split = n_wall = 0
    splits: list[tuple[int, int]] = []
    for n, es in list(inc.items()):
        kinds = {e.cls in inside_cls for e in es}
        if len(kinds) < 2 or n in gb.entrance:
            continue
        x, z = gb.nodes[n][:2]
        near_wall = False
        if walls is not None:
            near_wall = len(walls.query(Point(x, z), predicate="dwithin", distance=door_tol_m)) > 0
        # curated ac_link edges are snapped deliberately; their endpoints are treated as entrances
        if near_wall or any(e.curated for e in es):
            gb.curated_entrance.add(n)
            n_wall += 1
            continue
        new = next_id
        next_id -= 1
        gb.nodes[new] = gb.nodes[n]
        for e in es:
            if e.cls in inside_cls:
                if e.u == n:
                    e.u = new
                if e.v == n:
                    e.v = new
        splits.append((n, new))
        n_split += 1
    gb.log["entrance_split_nodes"] = n_split
    gb.log["entrance_wall_curated"] = n_wall
    rejoin_isolated(gb, splits)


def rejoin_isolated(gb: GraphBuild, splits: list[tuple[int, int]], min_edges: int = 10) -> None:
    """Conservative curated entrances (PRD 6.6): if splitting a non-entrance transition cut a region of
    >= ``min_edges`` walk edges off the main walk network, re-join it at ONE split node (the lowest node
    id, deterministic) and mark that node as a curated entrance. Repeats until no region can be re-joined.
    """
    rejoined: list[int] = []
    pending = list(splits)
    while True:
        parent: dict[int, int] = {}
        find = _make_find(parent)
        for e in gb.edges:
            if e.walk:
                ra, rb = find(e.u), find(e.v)
                if ra != rb:
                    parent[ra] = rb
        size: dict[int, int] = defaultdict(int)
        for e in gb.edges:
            if e.walk:
                size[find(e.u)] += 1
        if not size:
            break
        main = max(size, key=lambda k: size[k])
        pick: dict[int, tuple[int, int]] = {}
        for orig, new in sorted(pending):
            if orig not in gb.nodes or new not in gb.nodes:
                continue
            ca, cb = find(orig), find(new)
            if ca == cb or main not in (ca, cb):
                continue
            other = cb if ca == main else ca
            if size.get(other, 0) >= min_edges and other not in pick:
                pick[other] = (orig, new)
        if not pick:
            break
        for orig, new in pick.values():
            for e in gb.edges:
                if e.u == new:
                    e.u = orig
                if e.v == new:
                    e.v = orig
            gb.curated_entrance.add(orig)
            rejoined.append(orig)
            pending.remove((orig, new))
    gb.log["entrance_rejoined_curated"] = len(rejoined)
    gb.log["entrance_rejoined_nodes"] = rejoined


def _make_find(parent: dict[int, int]) -> Callable[[int], int]:
    def find(a: int) -> int:
        while parent.setdefault(a, a) != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    return find


def largest_components(gb: GraphBuild) -> dict[str, int]:
    """Keep the largest connected component per mode; return dropped component counts."""
    dropped: dict[str, int] = {}
    keep_mode: dict[str, set[int]] = {}
    for mode in ("walk", "cycle"):
        parent: dict[int, int] = {}
        find = _make_find(parent)
        idx = [i for i, e in enumerate(gb.edges) if getattr(e, mode)]
        for i in idx:
            e = gb.edges[i]
            ra, rb = find(e.u), find(e.v)
            if ra != rb:
                parent[ra] = rb
        comp_size: dict[int, int] = defaultdict(int)
        for i in idx:
            comp_size[find(gb.edges[i].u)] += 1
        if not comp_size:
            dropped[mode] = 0
            keep_mode[mode] = set()
            continue
        best = max(comp_size, key=lambda k: comp_size[k])
        dropped[mode] = len(comp_size) - 1
        keep_mode[mode] = {i for i in idx if find(gb.edges[i].u) == best}
    new_edges = []
    for i, e in enumerate(gb.edges):
        e.walk = e.walk and i in keep_mode["walk"]
        e.cycle = e.cycle and i in keep_mode["cycle"]
        if e.walk or e.cycle:
            new_edges.append(e)
    gb.log["dropped_edges_lcc"] = len(gb.edges) - len(new_edges)
    gb.edges = new_edges
    return dropped


def to_columnar(gb: GraphBuild) -> tuple[dict[str, Any], dict[int, int]]:
    used = sorted({n for e in gb.edges for n in (e.u, e.v)}, key=lambda n: (n < 0, abs(n)))
    remap = {n: i for i, n in enumerate(used)}
    nodes = {"x": [], "z": [], "lat": [], "lon": [], "entrance": [], "crossing": [], "osm": []}
    for n in used:
        x, z, la, lo = gb.nodes[n]
        nodes["x"].append(round(x, 2))
        nodes["z"].append(round(z, 2))
        nodes["lat"].append(round(la, 7))
        nodes["lon"].append(round(lo, 7))
        nodes["entrance"].append(n in gb.entrance or n in gb.curated_entrance)
        nodes["crossing"].append(n in gb.crossing)
        nodes["osm"].append(n if n > 0 else None)
    keys = [
        "u",
        "v",
        "length_m",
        "highway",
        "cls",
        "stairs",
        "walk",
        "cycle",
        "scooter",
        "name",
        "osm",
        "geom",
        "curated",
        "verified",
        "layer",
    ]
    edges: dict[str, list[Any]] = {k: [] for k in keys}
    for e in gb.edges:
        edges["u"].append(remap[e.u])
        edges["v"].append(remap[e.v])
        edges["length_m"].append(round(e.length, 2))
        edges["highway"].append(e.tags.get("highway"))
        edges["cls"].append(e.cls)
        stairs = e.tags.get("highway") == "steps"
        edges["stairs"].append(stairs)
        edges["walk"].append(e.walk)
        cyc = e.cycle and not stairs
        edges["cycle"].append(cyc)
        edges["scooter"].append(cyc)
        edges["name"].append(e.name)
        edges["osm"].append(e.osm)
        edges["geom"].append([round(v, 2) for p in e.geom for v in p])
        edges["curated"].append(e.curated)
        edges["verified"].append(e.verified)
        try:
            edges["layer"].append(int(float(e.tags.get("layer", "0").split(";")[0])))
        except ValueError:
            edges["layer"].append(0)
    return {"nodes": nodes, "edges": edges}, remap


def nearest_node(gb: GraphBuild, x: float, z: float, mode: str = "walk") -> tuple[int, float]:
    best, bd = -1, math.inf
    for e in gb.edges:
        if not getattr(e, mode):
            continue
        for n in (e.u, e.v):
            nx, nz = gb.nodes[n][:2]
            d = (nx - x) ** 2 + (nz - z) ** 2
            if d < bd:
                best, bd = n, d
    return best, math.sqrt(bd)


ENTRANCE_LINK_M = 40.0


def link_entrances(
    gb: GraphBuild, building_polys: list[Polygon], max_m: float = ENTRANCE_LINK_M
) -> list[dict]:
    """Connect OSM ``entrance=*`` doors whose outdoor (or indoor) side is not mapped.

    * entrance node with indoor edges but no outdoor edge -> short straight ``entrance_link`` edge to the
      nearest outdoor walk node within ``max_m``;
    * entrance node on no way at all -> links to the nearest outdoor AND nearest indoor walk node.
    A link is rejected if more than 2 m of it runs through a building footprint (would walk through
    walls). Links are cls ``open``, walk-only, ``curated=True, verified=False``.
    """
    inside_cls = {"indoor", "ac_link"}
    inc: dict[int, set[str]] = defaultdict(set)
    upper: set[int] = set()  # nodes on bridges / upper or lower floors: never linked to street level
    for e in gb.edges:
        if e.walk:
            k = "in" if e.cls in inside_cls else "out"
            inc[e.u].add(k)
            inc[e.v].add(k)
            lvl = str(e.tags.get("level", "0")).split(";")
            if e.cls == "ac_link" or _is_elevated(e.tags) or any(x.strip() not in ("0", "") for x in lvl):
                upper.update((e.u, e.v))
    out_nodes = sorted(n for n, k in inc.items() if "out" in k)
    in_nodes = sorted(n for n, k in inc.items() if "in" in k)
    if not out_nodes:
        return []
    from scipy.spatial import cKDTree

    t_out = cKDTree(np.array([gb.nodes[n][:2] for n in out_nodes]))
    t_in = cKDTree(np.array([gb.nodes[n][:2] for n in in_nodes])) if in_nodes else None
    walls = shapely.STRtree(building_polys) if building_polys else None

    def blocked(a: tuple[float, float], b: tuple[float, float]) -> bool:
        if walls is None:
            return False
        seg = LineString([a, b])
        inside = sum(building_polys[i].intersection(seg).length for i in walls.query(seg))
        return inside > 2.0

    report: list[dict] = []
    gb.log["entrance_unlinked"] = []

    def add(src: int, tree: Any, pool: list[int], side: str) -> None:
        xy = gb.nodes[src][:2]
        for d, j in zip(*tree.query(xy, k=4), strict=True):
            if not np.isfinite(d) or d > max_m:
                break
            dst = pool[int(j)]
            if dst == src or (side == "out" and blocked(xy, gb.nodes[dst][:2])):
                continue
            e = Edge(
                src,
                dst,
                [xy, gb.nodes[dst][:2]],
                {"highway": "footway", "entrance_link": "yes"},
                "curated/entrance_link",
                True,
                False,
                cls="open" if side == "out" else "indoor",
                curated=True,
                verified=False,
            )
            if e.length > 0.05:
                gb.edges.append(e)
                report.append({"entrance": src, "to": dst, "side": side, "length_m": round(e.length, 1)})
            return
        gb.log["entrance_unlinked"].append(src)

    for n in sorted(gb.entrance):
        k = inc.get(n, set())
        if "in" in k and "out" not in k and n not in upper:
            add(n, t_out, out_nodes, "out")
    for n, v in sorted(gb.free_entrance.items()):
        if t_in is None:
            break
        dn_out = t_out.query(v[:2])[0]
        dn_in = t_in.query(v[:2])[0]
        if dn_out <= max_m and dn_in <= max_m:
            gb.nodes[n] = v
            gb.entrance.add(n)
            add(n, t_in, in_nodes, "in")
            add(n, t_out, out_nodes, "out")
    gb.log["entrance_links"] = len(report)
    return report

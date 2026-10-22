"""Graph arrays, per-mode directed CSR adjacency and node snapping (PRD 6.5, 8.2).

Edge index i (position in graph.json arrays) is THE edge id everywhere (CONTRACTS 3).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.spatial import cKDTree

from zill import config
from zill.routing import modes as M


class NoRoute(Exception):
    """No path between the snapped origin and destination for this mode."""


class PlaceError(ValueError):
    """A place could not be resolved or lies outside the baked graph."""


@dataclass
class ModeGraph:
    """Directed adjacency for one mode (both directions of each undirected edge)."""

    mode: str
    ptr: list[int]
    to: list[int]
    edge: list[int]
    base_t: list[float]  # per EDGE: traversal seconds (length/speed, stairs factor, crowd), no wait
    pen_w: list[float]  # per EDGE: sun_weight(mode) * comfort(cls)
    open_mask: list[bool]  # per EDGE: sun exposure applies (cls == open)
    allowed: np.ndarray  # bool per edge
    node_ids: np.ndarray  # nodes with >=1 arc (snap candidates)
    kd: cKDTree | None = None
    wait: list[float] = field(default_factory=list)  # per NODE: crossing wait seconds


@dataclass
class GraphArrays:
    x: np.ndarray
    z: np.ndarray
    lat: np.ndarray
    lon: np.ndarray
    entrance: np.ndarray
    crossing: np.ndarray
    eu: np.ndarray
    ev: np.ndarray
    length: np.ndarray
    cls: np.ndarray  # int8 codes (modes.CLS_*)
    cls_name: list[str]
    stairs: np.ndarray
    allowed: dict[str, np.ndarray]
    name: list[str | None]
    highway: list[str]
    geom: list[list[float]]
    osm: list[str]
    _mode_graphs: dict[str, ModeGraph] = field(default_factory=dict)

    @property
    def n_nodes(self) -> int:
        return int(self.x.shape[0])

    @property
    def n_edges(self) -> int:
        return int(self.eu.shape[0])

    @classmethod
    def from_json(cls, g: dict) -> GraphArrays:
        nd, ed = g["nodes"], g["edges"]
        cls_names = [str(c) for c in ed["cls"]]
        cls_codes = np.array([M.CLS_CODES.get(c, M.CLS_OPEN) for c in cls_names], dtype=np.int8)
        stairs = np.array(ed["stairs"], dtype=bool)
        walk = np.array(ed["walk"], dtype=bool)
        cyc = np.array(ed["cycle"], dtype=bool) & ~stairs
        sco = np.array(ed.get("scooter", ed["cycle"]), dtype=bool) & ~stairs
        n = len(ed["u"])
        return cls(
            x=np.asarray(nd["x"], dtype=np.float64),
            z=np.asarray(nd["z"], dtype=np.float64),
            lat=np.asarray(nd["lat"], dtype=np.float64),
            lon=np.asarray(nd["lon"], dtype=np.float64),
            entrance=np.asarray(nd.get("entrance", [False] * len(nd["x"])), dtype=bool),
            crossing=np.asarray(nd.get("crossing", [False] * len(nd["x"])), dtype=bool),
            eu=np.asarray(ed["u"], dtype=np.int64),
            ev=np.asarray(ed["v"], dtype=np.int64),
            length=np.asarray(ed["length_m"], dtype=np.float64),
            cls=cls_codes,
            cls_name=cls_names,
            stairs=stairs,
            allowed={"walk": walk, "cycle": cyc, "scooter": sco},
            name=list(ed.get("name", [None] * n)),
            highway=list(ed.get("highway", [""] * n)),
            geom=list(ed.get("geom", [[] for _ in range(n)])),
            osm=list(ed.get("osm", [""] * n)),
        )

    def mode_graph(self, mode: str) -> ModeGraph:
        M.check_mode(mode)
        mg = self._mode_graphs.get(mode)
        if mg is None:
            mg = self._build_mode(mode)
            self._mode_graphs[mode] = mg
        return mg

    def _build_mode(self, mode: str) -> ModeGraph:
        allowed = self.allowed[mode]
        ids = np.nonzero(allowed)[0]
        src = np.concatenate([self.eu[ids], self.ev[ids]])
        dst = np.concatenate([self.ev[ids], self.eu[ids]])
        eid = np.concatenate([ids, ids])
        order = np.argsort(src, kind="stable")
        src, dst, eid = src[order], dst[order], eid[order]
        ptr = np.zeros(self.n_nodes + 1, dtype=np.int64)
        np.add.at(ptr, src + 1, 1)
        ptr = np.cumsum(ptr)

        speed = config.SPEEDS[mode]
        crowd = np.array([config.CROWD.get(M.CLS_NAMES[int(c)], 1.0) for c in self.cls], dtype=float)
        comfort = np.array([config.COMFORT.get(M.CLS_NAMES[int(c)], 1.0) for c in self.cls], dtype=float)
        t = self.length / speed * crowd
        if mode == "walk":
            t = np.where(self.stairs, t / config.STAIRS_WALK_FACTOR, t)
        wait = np.where(self.crossing, config.CROSSING_WAIT_S[mode], 0.0)
        node_ids = np.unique(src) if src.size else np.array([], dtype=np.int64)
        kd = cKDTree(np.column_stack([self.x[node_ids], self.z[node_ids]])) if node_ids.size else None
        return ModeGraph(
            mode=mode,
            ptr=ptr.tolist(),
            to=dst.tolist(),
            edge=eid.tolist(),
            base_t=t.tolist(),
            pen_w=(config.SUN_WEIGHT[mode] * comfort).tolist(),
            open_mask=(self.cls == M.CLS_OPEN).tolist(),
            allowed=allowed,
            node_ids=node_ids,
            kd=kd,
            wait=wait.tolist(),
        )

    def snap(self, x: float, z: float, mode: str, max_dist_m: float = 400.0) -> tuple[int, float]:
        """Nearest routable node (in `mode`) to local (x, z). Returns (node, distance_m)."""
        mg = self.mode_graph(mode)
        if mg.kd is None:
            raise PlaceError(f"no routable nodes for mode {mode}")
        d, i = mg.kd.query([x, z])
        if d > max_dist_m:
            raise PlaceError(f"point is {d:.0f} m from the nearest {mode} path (limit {max_dist_m:.0f} m)")
        return int(mg.node_ids[int(i)]), float(d)

    def edge_geom_oriented(self, e: int, from_node: int) -> list[list[float]]:
        """Edge geometry [[x,z],...] oriented to start at `from_node`."""
        flat = self.geom[e]
        pts = [[float(flat[k]), float(flat[k + 1])] for k in range(0, len(flat) - 1, 2)]
        if len(pts) < 2:
            pts = [
                [float(self.x[self.eu[e]]), float(self.z[self.eu[e]])],
                [float(self.x[self.ev[e]]), float(self.z[self.ev[e]])],
            ]
        if int(self.eu[e]) == from_node:
            return pts
        return pts[::-1]

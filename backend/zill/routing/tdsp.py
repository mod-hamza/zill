"""Time-dependent A* shade router (PRD 8.1-8.3).

cost_e = t_e + t_e * lam * w_m * sun_e(tau) * uv(tau) * comfort_e    (>= t_e: h = dist/speed is admissible)

* t_e: traversal seconds = length/speed (x stairs factor for walk, x crowd for indoor/ac_link)
  plus the crossing wait when LEAVING a crossing node (not the origin).
* tau: clock time at which the traveller reaches the edge's start node (arrival-time lookup);
  sun_e(tau) is linearly interpolated between the two nearest 10-minute exposure steps.
* Only the penalty depends on the sun; travel time never does (FIFO holds for time).
* Exposure applies only to `open` edges; covered/indoor/ac_link edges are always sun-free.

Sun mode (preference="sun", overnight Stream A) minimises the mirror image without negative weights:

cost_e = t_e + lam * W_m * shade_time_e(tau),   shade_time_e = t_e * (1 - sun_e(tau)) on open edges,
                                                shade_time_e = t_e on covered / indoor / ac_link edges

W_m = config.SUN_WEIGHT[mode] (no comfort bonus for indoor links, no UV factor). Costs stay >= t_e, so
the same straight-line heuristic stays admissible. Shade mode is unchanged.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Literal

import numpy as np

from zill import config
from zill.geo import to_wgs84
from zill.routing import modes as M
from zill.routing.graph import GraphArrays, ModeGraph, NoRoute, PlaceError
from zill.routing.heat import rhl_edge
from zill.routing.suntable import SunTable
from zill.services import CityContext

Preference = Literal["shade", "sun"]
PREFERENCES = ("shade", "sun")


def check_preference(preference: str) -> str:
    if preference not in PREFERENCES:
        raise ValueError(f"unknown preference {preference!r}; expected one of {PREFERENCES}")
    return preference


@dataclass
class RouteResult:
    lam: float
    label: str
    mode: str
    depart: datetime
    stats: dict[str, Any]
    nodes: list[int]
    edges: list[int]
    segments: list[dict[str, Any]]
    arrival_s: list[float] = field(default_factory=list)  # per-vertex arrival seconds after departure
    date_key: str = ""

    def to_dict(self, include_segments: bool = True) -> dict[str, Any]:
        return {
            "lambda": self.lam,
            "label": self.label,
            "mode": self.mode,
            "depart": self.depart.isoformat(),
            "stats": self.stats,
            "nodes": self.nodes,
            "edges": self.edges,
            "arrival_s": [round(a, 2) for a in self.arrival_s],
            "segments": self.segments if include_segments else [],
        }

    def summary(self) -> dict[str, Any]:
        return {"lambda": self.lam, "label": self.label, "stats": self.stats}


def _node(x: Any) -> int:
    if isinstance(x, dict):
        return int(x["node"])
    return int(x)


def _stat_round(stats: dict[str, Any]) -> dict[str, Any]:
    return {k: (round(v, 2) if isinstance(v, float) else v) for k, v in stats.items()}


# ---------------------------------------------------------------------------------------------
# Path evaluation (replays timing exactly like the search so numbers agree)
# ---------------------------------------------------------------------------------------------
def evaluate_path(
    g: GraphArrays,
    mg: ModeGraph,
    tab: SunTable,
    nodes: list[int],
    edges: list[int],
    depart_min: float,
    with_geometry: bool = True,
    origin_ll: dict[str, float] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[float]]:
    """Return (stats-without-relative-fields, segments, per-vertex arrival seconds)."""
    el = 0.0
    arr = [0.0]
    dist = dur = sun_s = covered_s = indoor_s = rhl = 0.0
    segs: list[dict[str, Any]] = []
    for idx, e in enumerate(edges):
        u = nodes[idx]
        wait = mg.wait[u] if idx > 0 else 0.0
        t = mg.base_t[e] + wait
        cname = M.CLS_NAMES[int(g.cls[e])]
        s = tab.sun(e, depart_min + el / 60.0) if mg.open_mask[e] else 0.0
        s = float(min(1.0, max(0.0, s)))
        dist += float(g.length[e])
        dur += t
        sun_s += s * t
        if cname == "covered":
            covered_s += t
        elif cname in ("indoor", "ac_link"):
            indoor_s += t
        rhl += rhl_edge(t, s, cname)
        if with_geometry:
            geom = g.edge_geom_oriented(e, u)
            ll = [list(to_wgs84(p[0], p[1], origin_ll)) for p in geom] if origin_ll else []
            segs.append(
                {
                    "edge": int(e),
                    "geometry": [[round(p[0], 2), round(p[1], 2)] for p in geom],
                    "latlon": [[round(a, 6), round(b, 6)] for a, b in ll],
                    "arrival_s": round(el, 2),
                    "t_s": round(t, 2),
                    "sun": round(s, 3),
                    "cls": cname,
                    "name": g.name[e],
                }
            )
        el += t
        arr.append(el)
    pct = (lambda a: 100.0 * a / dur) if dur > 0 else (lambda a: 0.0)
    stats = {
        "distance_m": dist,
        "duration_s": dur,
        "sun_exposure_s": sun_s,
        "shaded_pct": 100.0 - pct(sun_s) if dur > 0 else 0.0,
        "covered_pct": pct(covered_s),
        "indoor_pct": pct(indoor_s),
        "rhl": rhl,
    }
    return stats, segs, arr


def _finish(res_stats: dict[str, Any], fastest: dict[str, Any] | None) -> dict[str, Any]:
    st = dict(res_stats)
    if fastest is None:
        st.update(added_time_s=0.0, sun_saved_s=0.0, sun_saved_pct=0.0, rhl_saved_pct=0.0)
    else:
        st["added_time_s"] = st["duration_s"] - fastest["duration_s"]
        st["sun_saved_s"] = fastest["sun_exposure_s"] - st["sun_exposure_s"]
        st["sun_saved_pct"] = (
            100.0 * st["sun_saved_s"] / fastest["sun_exposure_s"] if fastest["sun_exposure_s"] > 0 else 0.0
        )
        st["rhl_saved_pct"] = (
            100.0 * (fastest["rhl"] - st["rhl"]) / fastest["rhl"] if fastest["rhl"] > 0 else 0.0
        )
    return _stat_round(st)


def _finish_pref(
    res_stats: dict[str, Any], fastest: dict[str, Any] | None, preference: str
) -> dict[str, Any]:
    """`_finish` plus, in sun mode, `sun_gained_s` / `sun_gained_pct` versus the fastest route."""
    st = _finish(res_stats, fastest)
    if preference != "sun":
        return st
    if fastest is None:
        st.update(sun_gained_s=0.0, sun_gained_pct=0.0)
    else:
        gained = float(res_stats["sun_exposure_s"]) - float(fastest["sun_exposure_s"])
        st["sun_gained_s"] = round(gained, 2)
        st["sun_gained_pct"] = (
            round(100.0 * gained / fastest["sun_exposure_s"], 2) if fastest["sun_exposure_s"] > 0 else 0.0
        )
    return st


# ---------------------------------------------------------------------------------------------
# The search
# ---------------------------------------------------------------------------------------------
def _search(
    g: GraphArrays,
    mg: ModeGraph,
    tab: SunTable,
    o: int,
    d: int,
    depart_min: float,
    lam: float,
    speed: float,
    blocked: frozenset[int] = frozenset(),
    sun_w: float | None = None,
) -> tuple[list[int], list[int]]:
    """A* search. `sun_w` (sun mode only) = SUN_WEIGHT[mode]: the cost becomes t + lam*sun_w*shade_time."""
    if sun_w is not None:
        return _search_sun(g, mg, tab, o, d, depart_min, lam, speed, blocked, sun_w)
    n_nodes = g.n_nodes
    if mg.ptr[o + 1] == mg.ptr[o] or mg.ptr[d + 1] == mg.ptr[d]:
        if o != d:
            raise NoRoute("origin or destination is not on a path for this mode")
    ptr, to, edge = mg.ptr, mg.to, mg.edge
    base_t, pen_w, open_mask, waitv = mg.base_t, mg.pen_w, mg.open_mask, mg.wait
    fl, n_steps, m0, inv = tab.flat, tab.n, tab.m0, 1.0 / tab.step
    uvl = tab.uv_list
    kmax = max(n_steps - 2, 0)

    # admissible heuristic: straight-line seconds (cost >= travel time >= length/speed)
    h = (np.hypot(g.x - g.x[d], g.z - g.z[d]) / speed).tolist()

    INF = math.inf
    gc = [INF] * n_nodes
    el = [0.0] * n_nodes
    pe = [-1] * n_nodes
    pn = [-1] * n_nodes
    gc[o] = 0.0
    heap: list[tuple[float, float, int]] = [(h[o], 0.0, o)]
    pop, push = heapq.heappop, heapq.heappush
    use_pen = lam > 0.0 and n_steps >= 2
    while heap:
        _, c, u = pop(heap)
        if c > gc[u]:
            continue
        if u == d:
            break
        eu_ = el[u]
        wait = waitv[u] if u != o else 0.0
        if use_pen:
            pos = (depart_min + eu_ / 60.0 - m0) * inv
            if pos <= 0.0:
                k, fr = 0, 0.0
            elif pos >= kmax + 1:
                k, fr = kmax, 1.0
            else:
                k = int(pos)
                fr = pos - k
            a_uv = uvl[k]
            lamuv = lam * (a_uv + (uvl[k + 1] - a_uv) * fr)
        for a in range(ptr[u], ptr[u + 1]):
            e = edge[a]
            if blocked and e in blocked:
                continue
            v = to[a]
            t = base_t[e] + wait
            if use_pen and open_mask[e]:
                i = e * n_steps + k
                s0 = fl[i]
                s = s0 + (fl[i + 1] - s0) * fr
                nc = c + t + t * lamuv * pen_w[e] * s
            else:
                nc = c + t
            if nc < gc[v]:
                gc[v] = nc
                el[v] = eu_ + t
                pe[v] = e
                pn[v] = u
                push(heap, (nc + h[v], nc, v))
    if gc[d] == INF:
        raise NoRoute("no path between origin and destination for this mode")
    nodes = [d]
    edges: list[int] = []
    cur = d
    while cur != o:
        edges.append(pe[cur])
        cur = pn[cur]
        nodes.append(cur)
    nodes.reverse()
    edges.reverse()
    return nodes, edges


def _search_sun(
    g: GraphArrays,
    mg: ModeGraph,
    tab: SunTable,
    o: int,
    d: int,
    depart_min: float,
    lam: float,
    speed: float,
    blocked: frozenset[int],
    sun_w: float,
) -> tuple[list[int], list[int]]:
    """Sun-mode A*: cost = t + lam*W*shade_time (>= t, so the straight-line heuristic is admissible)."""
    n_nodes = g.n_nodes
    if mg.ptr[o + 1] == mg.ptr[o] or mg.ptr[d + 1] == mg.ptr[d]:
        if o != d:
            raise NoRoute("origin or destination is not on a path for this mode")
    ptr, to, edge = mg.ptr, mg.to, mg.edge
    base_t, open_mask, waitv = mg.base_t, mg.open_mask, mg.wait
    fl, n_steps, m0, inv = tab.flat, tab.n, tab.m0, 1.0 / tab.step
    kmax = max(n_steps - 2, 0)
    h = (np.hypot(g.x - g.x[d], g.z - g.z[d]) / speed).tolist()

    INF = math.inf
    gc = [INF] * n_nodes
    el = [0.0] * n_nodes
    pe = [-1] * n_nodes
    pn = [-1] * n_nodes
    gc[o] = 0.0
    heap: list[tuple[float, float, int]] = [(h[o], 0.0, o)]
    pop, push = heapq.heappop, heapq.heappush
    lw = lam * sun_w
    use_pen = lw > 0.0
    have_tab = n_steps >= 2
    k, fr = 0, 0.0
    while heap:
        _, c, u = pop(heap)
        if c > gc[u]:
            continue
        if u == d:
            break
        eu_ = el[u]
        wait = waitv[u] if u != o else 0.0
        if use_pen and have_tab:
            pos = (depart_min + eu_ / 60.0 - m0) * inv
            if pos <= 0.0:
                k, fr = 0, 0.0
            elif pos >= kmax + 1:
                k, fr = kmax, 1.0
            else:
                k = int(pos)
                fr = pos - k
        for a in range(ptr[u], ptr[u + 1]):
            e = edge[a]
            if blocked and e in blocked:
                continue
            v = to[a]
            t = base_t[e] + wait
            if use_pen:
                if open_mask[e]:
                    if have_tab:
                        i = e * n_steps + k
                        s0 = fl[i]
                        s = s0 + (fl[i + 1] - s0) * fr
                    else:
                        s = fl[e * n_steps] if n_steps else 0.0
                    s = 0.0 if s < 0.0 else (1.0 if s > 1.0 else s)
                    nc = c + t + lw * t * (1.0 - s)
                else:
                    nc = c + t + lw * t
            else:
                nc = c + t
            if nc < gc[v]:
                gc[v] = nc
                el[v] = eu_ + t
                pe[v] = e
                pn[v] = u
                push(heap, (nc + h[v], nc, v))
    if gc[d] == INF:
        raise NoRoute("no path between origin and destination for this mode")
    nodes = [d]
    edges: list[int] = []
    cur = d
    while cur != o:
        edges.append(pe[cur])
        cur = pn[cur]
        nodes.append(cur)
    nodes.reverse()
    edges.reverse()
    return nodes, edges


_BASELINE: dict[tuple, dict[str, Any]] = {}


def _bkey(
    ctx: CityContext, o: int, d: int, mode: str, depart: datetime, date_key: str, blocked: frozenset[int]
) -> tuple:
    return (ctx.city_id, id(ctx), o, d, mode, depart.isoformat(), ctx.date_for(date_key)[0], blocked)


def route(
    ctx: CityContext,
    origin_node: Any,
    dest_node: Any,
    mode: str,
    depart: datetime,
    lam: float,
    date_key: str,
    label: str | None = None,
    with_geometry: bool = True,
    blocked_edges: frozenset[int] | set[int] = frozenset(),
    relative: bool = True,
    preference: str = "shade",
) -> RouteResult:
    """Single time-dependent A* route.

    `preference="sun"` minimises time + lam*W*shade_time instead (most direct sun); see module doc.

    With `relative=True` the stats carry added_time_s / sun_saved_* / rhl_saved_pct against the fastest
    route (lam=0) for the same query (computed once and cached); `compare` is the canonical entry point
    for the Fastest / Balanced / Coolest triple (it also applies the honesty rule).
    `blocked_edges` removes edges from the graph (closures for replanning).
    """
    M.check_mode(mode)
    check_preference(preference)
    sun_w = float(config.SUN_WEIGHT[mode]) if preference == "sun" else None
    o, d = _node(origin_node), _node(dest_node)
    g = ctx.graph
    if not (0 <= o < g.n_nodes and 0 <= d < g.n_nodes):
        raise PlaceError("node id out of range")
    blocked = frozenset(int(e) for e in blocked_edges)
    mg = g.mode_graph(mode)
    tab = ctx.exposure(date_key)
    dmin = tab.minute_of(depart)

    def run(lam_: float) -> tuple[list[int], list[int]]:
        if o == d:
            return [o], []
        if sun_w is not None and lam_ > 0:
            return _search(g, mg, tab, o, d, dmin, float(lam_), config.SPEEDS[mode], blocked, sun_w)
        return _search(g, mg, tab, o, d, dmin, float(lam_), config.SPEEDS[mode], blocked)

    nodes, edges = run(lam)
    stats, segs, arr = evaluate_path(g, mg, tab, nodes, edges, dmin, with_geometry, ctx.origin)
    base = None
    if relative:
        key = _bkey(ctx, o, d, mode, depart, date_key, blocked)
        if lam <= 0:
            base = stats
            _BASELINE[key] = stats
            if len(_BASELINE) > 512:
                _BASELINE.pop(next(iter(_BASELINE)))
        else:
            base = _BASELINE.get(key)
            if base is None:
                fn, fe = run(0.0)
                base, _, _ = evaluate_path(g, mg, tab, fn, fe, dmin, False, None)
                _BASELINE[key] = base
    return RouteResult(
        lam=float(lam),
        label=label or _label_for(lam, preference),
        mode=mode,
        depart=depart,
        stats=_finish_pref(stats, None if lam <= 0 else base, preference),
        nodes=nodes,
        edges=edges,
        segments=segs,
        arrival_s=arr,
        date_key=date_key,
    )


def _label_for(lam: float, preference: str = "shade") -> str:
    if lam <= 0:
        return "fastest"
    if lam <= 1.5:
        return "balanced"
    return "sunniest" if preference == "sun" else "coolest"


def best_label(preference: str) -> str:
    """Key of the lam=3 route in a compare() result: 'coolest' (shade) or 'sunniest' (sun)."""
    return "sunniest" if preference == "sun" else "coolest"


def compare(
    ctx: CityContext,
    o: Any,
    d: Any,
    mode: str,
    depart: datetime,
    date_key: str,
    lambdas: tuple[float, float, float] | list[float] = (0.0, 1.0, 3.0),
    with_geometry: bool = True,
    blocked_edges: frozenset[int] | set[int] = frozenset(),
    preference: str = "shade",
) -> dict[str, RouteResult]:
    """Fastest / balanced / coolest with relative stats and the honesty rule.

    `preference="sun"` returns fastest / balanced / sunniest instead (see `compare_sun`).

    "Coolest" is the lowest-RHL route among {lam=3, lam=1, fastest} whose sun exposure does not
    exceed the fastest route's. Under time-dependent exposure the lam=3 path can occasionally be
    hotter than the lam=1 path; in that case the better one is reported and `stats.note` says so.
    """
    if check_preference(preference) == "sun":
        return compare_sun(ctx, o, d, mode, depart, date_key, lambdas, with_geometry, blocked_edges)
    lf, lb, lc = (float(x) for x in lambdas)
    kw = {"with_geometry": with_geometry, "blocked_edges": blocked_edges, "relative": False}
    fastest = route(ctx, o, d, mode, depart, lf, date_key, "fastest", **kw)
    balanced = route(ctx, o, d, mode, depart, lb, date_key, "balanced", **kw)
    coolest = route(ctx, o, d, mode, depart, lc, date_key, "coolest", **kw)
    fs = fastest.stats
    # recompute relative stats against fastest (absolute stats already rounded in .stats)
    for r in (fastest, balanced, coolest):
        r.stats = _finish(
            {
                k: v
                for k, v in r.stats.items()
                if k not in ("added_time_s", "sun_saved_s", "sun_saved_pct", "rhl_saved_pct", "note")
            },
            fs,
        )
    note = None
    eps = 1e-6
    eligible = [r for r in (coolest, balanced) if r.stats["sun_exposure_s"] <= fs["sun_exposure_s"] + eps]
    best = min([*eligible, fastest], key=lambda r: (r.stats["rhl"], r is not coolest))
    if best is not coolest:
        if best is fastest:
            note = (
                "No cooler route found for this departure: the lower-sun alternatives cost more heat load "
                "than the fastest route; coolest = fastest."
            )
            best = replace(fastest, label="coolest")
        else:
            note = (
                "The lam=3 search was not cooler than the lam=1 search at this departure "
                "(exposure changes along the way); reporting the lowest-heat-load route found."
            )
            best = replace(balanced, label="coolest")
        best.stats = {**best.stats, "note": note}
        coolest = best
    fastest.label, balanced.label, coolest.label = "fastest", "balanced", "coolest"
    return {"fastest": fastest, "balanced": balanced, "coolest": coolest}


_SUN_RELATIVE_KEYS = (
    "added_time_s",
    "sun_saved_s",
    "sun_saved_pct",
    "rhl_saved_pct",
    "note",
    "sun_gained_s",
    "sun_gained_pct",
)


def compare_sun(
    ctx: CityContext,
    o: Any,
    d: Any,
    mode: str,
    depart: datetime,
    date_key: str,
    lambdas: tuple[float, float, float] | list[float] = (0.0, 1.0, 3.0),
    with_geometry: bool = True,
    blocked_edges: frozenset[int] | set[int] = frozenset(),
) -> dict[str, RouteResult]:
    """Fastest / balanced / sunniest (sun mode) with relative stats and the sun honesty rule.

    "Sunniest" is the route with the most direct-sun seconds among {lam=3, lam=1, fastest}. If the
    lam=3 search is beaten (exposure changes along the way) the better route is reported and
    `stats.note` says so; if no route gains sun over the fastest, sunniest = fastest with a note.
    """
    lf, lb, lc = (float(x) for x in lambdas)
    kw: dict[str, Any] = {
        "with_geometry": with_geometry,
        "blocked_edges": blocked_edges,
        "relative": False,
        "preference": "sun",
    }
    fastest = route(ctx, o, d, mode, depart, lf, date_key, "fastest", **kw)
    balanced = route(ctx, o, d, mode, depart, lb, date_key, "balanced", **kw)
    sunniest = route(ctx, o, d, mode, depart, lc, date_key, "sunniest", **kw)
    fs = {k: v for k, v in fastest.stats.items() if k not in _SUN_RELATIVE_KEYS}
    for r in (fastest, balanced, sunniest):
        base = {k: v for k, v in r.stats.items() if k not in _SUN_RELATIVE_KEYS}
        r.stats = _finish_pref(base, None if r is fastest else fs, "sun")
    eps = 1e-6
    no_gain = "No sunnier route found for this departure; sunniest = fastest."
    best = max((sunniest, balanced, fastest), key=lambda r: r.stats["sun_exposure_s"])
    if best.stats["sun_exposure_s"] > sunniest.stats["sun_exposure_s"] + eps:
        if best is fastest:
            best = replace(fastest, label="sunniest")
            best.stats = {**best.stats, "note": no_gain}
        else:
            best = replace(balanced, label="sunniest")
            best.stats = {
                **best.stats,
                "note": "The lam=3 search was not sunnier than the lam=1 search at this departure "
                "(exposure changes along the way); reporting the sunniest route found.",
            }
        sunniest = best
    elif sunniest.stats["sun_gained_s"] <= eps:
        sunniest.stats = {**sunniest.stats, "note": no_gain}
    fastest.label, balanced.label, sunniest.label = "fastest", "balanced", "sunniest"
    return {"fastest": fastest, "balanced": balanced, "sunniest": sunniest}


def uses_disallowed_edge(ctx: CityContext, r: RouteResult) -> bool:
    allowed = ctx.graph.allowed[r.mode]
    return any(not allowed[e] for e in r.edges)

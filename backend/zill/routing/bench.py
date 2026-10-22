"""Router timing benchmark: python -m zill.routing.bench [--city dubai_downtown | --synthetic 150] [--n 50].

Reports p50/p95/max wall time per single route (lam=3, the slowest case) and per compare() triple, over
random origin/destination pairs 300-1500 m apart.
"""

from __future__ import annotations

import argparse
import statistics
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np

from zill import config
from zill.geo import to_wgs84
from zill.routing import tdsp
from zill.routing.departure import optimise_departure
from zill.routing.graph import GraphArrays, NoRoute
from zill.routing.suntable import SunTable
from zill.services import CityContext, get_city


def synthetic_city(n: int, seed: int = 0) -> CityContext:
    """n x n grid (100 m spacing is too coarse; use 25 m blocks) with random smooth exposure."""
    rng = np.random.default_rng(seed)
    sp = 25.0
    xs, zs = [], []
    for j in range(n):
        for i in range(n):
            xs.append((i - n / 2) * sp)
            zs.append((j - n / 2) * sp)
    eu, ev = [], []
    for j in range(n):
        for i in range(n):
            u = j * n + i
            if i + 1 < n:
                eu.append(u)
                ev.append(u + 1)
            if j + 1 < n:
                eu.append(u)
                ev.append(u + n)
    ne = len(eu)
    origin = {"lat": config.ORIGIN_LAT, "lon": config.ORIGIN_LON}
    ll = [to_wgs84(x, z, origin) for x, z in zip(xs, zs, strict=True)]
    g = {
        "nodes": {
            "x": xs,
            "z": zs,
            "lat": [a for a, _ in ll],
            "lon": [b for _, b in ll],
            "entrance": [False] * len(xs),
            "crossing": (rng.random(len(xs)) < 0.05).tolist(),
        },
        "edges": {
            "u": eu,
            "v": ev,
            "length_m": [sp] * ne,
            "highway": ["footway"] * ne,
            "cls": ["open"] * ne,
            "stairs": [False] * ne,
            "walk": [True] * ne,
            "cycle": [True] * ne,
            "scooter": [True] * ne,
            "name": [None] * ne,
            "osm": [""] * ne,
            "geom": [[xs[a], zs[a], xs[b], zs[b]] for a, b in zip(eu, ev, strict=True)],
        },
    }
    ga = GraphArrays.from_json(g)
    mins = np.arange(360, 1141, 10, dtype=float)
    # blocky shade: low-frequency random field in space, drifting with time
    base = rng.random((ne, 1))
    drift = np.sin(mins[None, :] / 90.0 + base * 6.0)
    expo = np.clip(0.5 + 0.6 * drift, 0, 1).astype(np.float32)
    tab = SunTable.build("summer", "2026-07-15", "Asia/Dubai", mins, expo, origin["lat"], origin["lon"])
    meta: dict[str, Any] = {"origin": origin, "timezone": "Asia/Dubai", "dates": config.PRESET_DATES}
    ctx = CityContext("bench", Path("."), meta, ga, [])
    ctx._tables["summer"] = tab
    return ctx


def pairs(
    ctx: CityContext, n: int, lo: float = 300.0, hi: float = 1500.0, seed: int = 1
) -> list[tuple[int, int]]:
    rng = np.random.default_rng(seed)
    ids = ctx.graph.mode_graph("walk").node_ids
    g = ctx.graph
    out: list[tuple[int, int]] = []
    while len(out) < n:
        a, b = (int(x) for x in rng.choice(ids, 2, replace=False))
        d = float(np.hypot(g.x[a] - g.x[b], g.z[a] - g.z[b]))
        if lo <= d <= hi:
            out.append((a, b))
    return out


def bench(ctx: CityContext, n: int = 50, date_key: str = "summer") -> dict[str, Any]:
    ps = pairs(ctx, n)
    dep = ctx.at(date_key, "13:30")
    tdsp.route(
        ctx, ps[0][0], ps[0][1], "walk", dep, 3.0, date_key, with_geometry=False, relative=False
    )  # warm-up
    single, triple, geo = [], [], []
    for a, b in ps:
        try:
            t = time.perf_counter()
            tdsp.route(ctx, a, b, "walk", dep, 3.0, date_key, with_geometry=False, relative=False)
            single.append((time.perf_counter() - t) * 1000)
            t = time.perf_counter()
            tdsp.compare(ctx, a, b, "walk", dep, date_key, with_geometry=True)
            triple.append((time.perf_counter() - t) * 1000)
            t = time.perf_counter()
            tdsp.route(ctx, a, b, "walk", dep, 3.0, date_key, with_geometry=True, relative=True)
            geo.append((time.perf_counter() - t) * 1000)
        except NoRoute:
            continue

    def q(xs: list[float]) -> dict[str, float]:
        xs = sorted(xs)
        return {
            "p50_ms": round(statistics.median(xs), 1),
            "p95_ms": round(xs[min(len(xs) - 1, int(0.95 * len(xs)))], 1),
            "max_ms": round(xs[-1], 1),
        }

    a, b = ps[0]
    t = time.perf_counter()
    dres = optimise_departure(ctx, a, b, "walk", dep, dep + timedelta(minutes=90), date_key=date_key)
    dep_ms = (time.perf_counter() - t) * 1000
    return {
        "graph": {"nodes": ctx.graph.n_nodes, "edges": ctx.graph.n_edges},
        "pairs": len(single),
        "route_lam3": q(single),
        "route_lam3_with_segments_and_baseline": q(geo),
        "compare_triple": q(triple),
        "departure_19": {"ms": round(dep_ms, 1), "rows": len(dres.table)},
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default=None)
    ap.add_argument("--synthetic", type=int, default=0)
    ap.add_argument("--n", type=int, default=50)
    a = ap.parse_args()
    ctx = synthetic_city(a.synthetic) if a.synthetic else get_city(a.city or config.DEFAULT_CITY)
    import json

    print(json.dumps(bench(ctx, a.n), indent=1))

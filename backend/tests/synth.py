"""Synthetic city fixture builder (routing/API tests; no network, no baked data needed).

Layout: 6 columns x 5 rows grid, 100 m spacing, plus one stairs-only stub node.
  row 0 "North Boulevard"  open, sun 1.0 all day
  row 1 "Shady Lane"       open, sun 1.0 until 14:00 then 0.1 (a tower shadow arrives)
  row 2 "Middle Street"    open (foot-only for the first two edges), sun 0.9
  row 3 "Arcade Row"       open, one covered edge (2,3)-(3,3)
  row 4 "South Street"     ac_link between columns 1..4 (corridor), open at both ends
  verticals "Cross Street i": open, sun 0.8
  extra: stairs-only diagonal (0,0)-(1,1) (walk only), stairs stub node 30 off (5,4)
  crossing node at (3,1)
Run `python -m tests.synth` from backend/ to (re)write backend/tests/fixtures/synth_city/synth/.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from zill import config
from zill.geo import to_wgs84

CITY_ID = "synth"
FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "synth_city"
COLS, ROWS, SP = 6, 5, 100.0
ORIGIN = {"lat": config.ORIGIN_LAT, "lon": config.ORIGIN_LON}
DATES = {"winter": "2026-01-15", "spring": "2026-04-15", "summer": "2026-07-15", "hackathon": "2026-10-24"}
ROW_NAMES = ["North Boulevard", "Shady Lane", "Middle Street", "Arcade Row", "South Street"]
SHADE_START_MIN = 14 * 60  # row 1 turns shaded at 14:00 (linear ramp over one 10-min step)
FIRST_MIN, LAST_MIN, STEP = 6 * 60, 19 * 60, 10


def nid(i: int, j: int) -> int:
    return j * COLS + i


def build_synth_city(root: Path = FIXTURE_ROOT) -> Path:
    cdir = root / CITY_ID
    (cdir / "shade" / "summer").mkdir(parents=True, exist_ok=True)

    xs = [(i - 2.5) * SP for j in range(ROWS) for i in range(COLS)]
    zs = [(j - 2) * SP for j in range(ROWS) for i in range(COLS)]
    xs.append(xs[nid(5, 4)] + 40.0)
    zs.append(zs[nid(5, 4)] + 30.0)
    stub = len(xs) - 1  # node 30

    nodes_cross = [False] * len(xs)
    nodes_cross[nid(3, 1)] = True
    nodes_ent = [False] * len(xs)
    nodes_ent[nid(1, 4)] = nodes_ent[nid(4, 4)] = True

    E: dict[str, list] = {
        k: []
        for k in (
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
        )
    }
    sun_kind: list[str] = []

    def add(
        u, v, name, cls="open", highway="footway", stairs=False, walk=True, cycle=True, kind="v", length=None
    ):
        ln = length if length is not None else float(np.hypot(xs[u] - xs[v], zs[u] - zs[v]))
        E["u"].append(u)
        E["v"].append(v)
        E["length_m"].append(round(ln, 3))
        E["highway"].append(highway)
        E["cls"].append(cls)
        E["stairs"].append(stairs)
        E["walk"].append(walk)
        E["cycle"].append(cycle)
        E["scooter"].append(cycle)
        E["name"].append(name)
        E["osm"].append(f"way/{len(E['u'])}")
        E["geom"].append([xs[u], zs[u], xs[v], zs[v]])
        sun_kind.append(kind)

    for j in range(ROWS):
        for i in range(COLS - 1):
            kw: dict = {"kind": f"row{j}"}
            if j == 2 and i < 2:
                kw.update(cycle=False)  # foot-only
            if j == 3 and i == 2:
                kw.update(cls="covered", highway="footway")
            if j == 4 and 1 <= i <= 3:
                kw.update(cls="ac_link", highway="corridor")
            add(nid(i, j), nid(i + 1, j), ROW_NAMES[j], **kw)
    for i in range(COLS):
        for j in range(ROWS - 1):
            add(nid(i, j), nid(i, j + 1), f"Cross Street {i}", kind="col")
    add(nid(0, 0), nid(1, 1), "Stair Link", highway="steps", stairs=True, cycle=False, kind="row0")
    add(nid(5, 4), stub, "Stair Stub", highway="steps", stairs=True, cycle=False, kind="row0")

    n_edges = len(E["u"])
    mins = np.arange(FIRST_MIN, LAST_MIN + 1, STEP, dtype=np.int16)
    hhmm = np.array([(m // 60) * 100 + m % 60 for m in mins], dtype=np.int16)
    expo = np.zeros((n_edges, len(mins)), dtype=np.float16)
    for e, kind in enumerate(sun_kind):
        cls = E["cls"][e]
        if cls != "open":
            continue
        if kind == "row1":
            expo[e] = np.where(mins <= SHADE_START_MIN, 1.0, 0.1)
        elif kind == "row0":
            expo[e] = 1.0
        elif kind == "col":
            expo[e] = 0.8
        else:
            expo[e] = 0.9
    # outside daylight (<06:30, >18:30) the sun is low: fade to zero at the ends
    expo[:, 0] = 0.0
    expo[:, -1] = 0.0
    np.savez_compressed(cdir / "exposure_summer.npz", exposure=expo, hhmm=hhmm, minutes=mins)

    lat, lon = zip(*(to_wgs84(x, z, ORIGIN) for x, z in zip(xs, zs, strict=True)), strict=True)
    graph = {
        "nodes": {
            "x": xs,
            "z": zs,
            "lat": list(lat),
            "lon": list(lon),
            "entrance": nodes_ent,
            "crossing": nodes_cross,
        },
        "edges": E,
    }
    (cdir / "graph.json").write_text(json.dumps(graph))

    pois = [
        ("nw_corner", "North West Plaza", 0, 0, "landmark"),
        ("ne_corner", "North East Tower", 5, 0, "landmark"),
        ("mid_cafe", "Middle Cafe", 2, 2, "cafe"),
        ("arcade_mall", "Arcade Mall", 3, 3, "mall"),
        ("south_metro", "South Metro", 1, 4, "metro"),
        ("se_hotel", "South East Hotel", 5, 4, "hotel"),
        ("shady_park", "Shady Park", 4, 1, "park"),
    ]
    plist = []
    for pid, name, i, j, kind in pois:
        n = nid(i, j)
        plist.append(
            {
                "id": pid,
                "name": name,
                "lat": lat[n],
                "lon": lon[n],
                "x": xs[n],
                "z": zs[n],
                "node": n,
                "kind": kind,
                "source": "curated",
            }
        )
    (cdir / "pois.json").write_text(json.dumps({"pois": plist}))

    meta = {
        "city_id": CITY_ID,
        "name": "Synthetic Grid",
        "timezone": "Asia/Dubai",
        "origin": ORIGIN,
        "bbox_core": {"s": min(lat), "w": min(lon), "n": max(lat), "e": max(lon)},
        "bbox_caster": {"s": min(lat), "w": min(lon), "n": max(lat), "e": max(lon)},
        "bbox_scene": {"s": min(lat), "w": min(lon), "n": max(lat), "e": max(lon)},
        "core_grid": {"x0": -350.0, "z0": -300.0, "rows": 150, "cols": 175, "res_m": 2.0},
        "caster_grid": {"x0": -350.0, "z0": -300.0, "rows": 150, "cols": 175, "res_m": 2.0},
        "counts": {"buildings": 0, "nodes": len(xs), "edges": n_edges, "pois": len(plist)},
        "attribution": "synthetic test fixture",
        "dates": DATES,
        "build_log": [
            {"t_ms": 0, "step": "geocode", "count": 1, "label": "Synthetic"},
            {"t_ms": 40, "step": "graph", "count": n_edges, "label": "Graph"},
            {"t_ms": 80, "step": "ready", "count": n_edges, "label": "Ready"},
        ],
    }
    (cdir / "meta.json").write_text(json.dumps(meta, indent=1))

    # shade pngs: small, constant-ish rasters + index.json
    steps = []
    for m, hh in zip(mins, hhmm, strict=True):
        name = f"step_{int(hh):04d}.png"
        arr = np.full((150, 175), 200, dtype=np.uint8)
        Image.fromarray(arr, mode="L").save(cdir / "shade" / "summer" / name)
        steps.append(
            {
                "hhmm": f"{int(hh):04d}",
                "ts": f"2026-07-15T{int(m) // 60:02d}:{int(m) % 60:02d}:00+04:00",
                "alt": 45.0,
                "az": 180.0,
                "night": False,
                "file": name,
            }
        )
    (cdir / "shade" / "summer" / "index.json").write_text(
        json.dumps({"date": "2026-07-15", "date_id": "summer", "steps": steps})
    )
    (cdir / "shade" / "bake_log.json").write_text(
        json.dumps([{"t_ms": 120, "step": "shadow_precompute", "count": len(steps), "label": "Shade steps"}])
    )
    return cdir


if __name__ == "__main__":
    print(build_synth_city())

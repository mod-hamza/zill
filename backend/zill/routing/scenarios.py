"""Hero scenario auto-selection (PRD 8.6): search, never hand-pick, never fabricate.

    python -m zill.routing.scenarios --city dubai_downtown [--out data/scenarios/hero.json] [--serial]

All POI pairs 400-1500 m apart x departures {12:30,13:30,14:30,15:30} x {summer, hackathon} x walk
(+cycle) are routed Fastest vs Coolest. Candidates are ranked by `sun_saved_s` subject to
added_time <= 25% of the fastest duration and a detour ratio (distance) <= 1.35. If the best tourist
result saves < 90 s of sun, the search is widened (wider distance band, extra graph-derived places,
more departure times) and every attempt is logged in `hero.json["search"]`.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np

from zill import config
from zill.routing import tdsp
from zill.routing.departure import optimise_departure
from zill.routing.graph import NoRoute
from zill.services import CityContext, get_city

DEPARTS = ("12:30", "13:30", "14:30", "15:30")
DATES = ("summer", "hackathon")
MAX_ADDED_FRAC = 0.25
MAX_DETOUR = 1.35
MIN_TOURIST_SAVE_S = 90.0
CREW_MAX_STRAIGHT_M = 700.0

_WORKER_CTX: CityContext | None = None


def _init_worker(city_id: str, cities_dir: str | None) -> None:
    global _WORKER_CTX
    if cities_dir:
        os.environ["ZILL_CITIES_DIR"] = cities_dir
    _WORKER_CTX = get_city(city_id)


def _eval_job(job: tuple) -> dict[str, Any] | None:
    ctx = _WORKER_CTX
    assert ctx is not None
    return eval_pair(ctx, *job)


def eval_pair(
    ctx: CityContext, a: dict[str, Any], b: dict[str, Any], mode: str, date_id: str, hhmm: str
) -> dict[str, Any] | None:
    try:
        res = tdsp.compare(
            ctx, a["node"], b["node"], mode, ctx.at(date_id, hhmm), date_id, with_geometry=False
        )
    except NoRoute:
        return None
    f, c = res["fastest"].stats, res["coolest"].stats
    detour = c["distance_m"] / f["distance_m"] if f["distance_m"] > 0 else 1.0
    added_frac = c["added_time_s"] / f["duration_s"] if f["duration_s"] > 0 else 0.0
    return {
        "origin": a["id"],
        "dest": b["id"],
        "origin_name": a["name"],
        "dest_name": b["name"],
        "mode": mode,
        "date_id": date_id,
        "depart": hhmm,
        "straight_m": round(math.hypot(a["x"] - b["x"], a["z"] - b["z"]), 1),
        "fastest_distance_m": f["distance_m"],
        "fastest_duration_s": f["duration_s"],
        "fastest_sun_s": f["sun_exposure_s"],
        "fastest_rhl": f["rhl"],
        "coolest_duration_s": c["duration_s"],
        "coolest_sun_s": c["sun_exposure_s"],
        "coolest_rhl": c["rhl"],
        "sun_saved_s": c["sun_saved_s"],
        "sun_saved_pct": c["sun_saved_pct"],
        "added_time_s": c["added_time_s"],
        "added_frac": round(added_frac, 4),
        "detour_ratio": round(detour, 4),
        "rhl_saved_pct": c["rhl_saved_pct"],
        "coolest_indoor_pct": c["indoor_pct"],
        "coolest_covered_pct": c["covered_pct"],
        "eligible": added_frac <= MAX_ADDED_FRAC and detour <= MAX_DETOUR and c["sun_saved_s"] > 0,
    }


def _places(ctx: CityContext) -> list[dict[str, Any]]:
    out = []
    for p in ctx.pois:
        if p.get("node") is None:
            continue
        out.append(
            {
                "id": p["id"],
                "name": p["name"],
                "lat": p["lat"],
                "lon": p["lon"],
                "x": p["x"],
                "z": p["z"],
                "node": int(p["node"]),
                "kind": p.get("kind"),
            }
        )
    return out


def _graph_places(ctx: CityContext, n: int, existing: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extra places for widening: well-spread graph intersections (degree >= 3) not near an existing place."""
    g = ctx.graph
    mg = g.mode_graph("walk")
    deg = np.diff(np.array(mg.ptr))
    cand = np.nonzero(deg >= 3)[0]
    if cand.size == 0:
        return []
    rng = np.random.default_rng(0)
    pts = np.column_stack([g.x[cand], g.z[cand]])
    chosen: list[int] = []
    taken = np.array([[p["x"], p["z"]] for p in existing]) if existing else np.zeros((0, 2))
    for _ in range(n):
        d = (
            np.min(np.hypot(pts[:, None, 0] - taken[None, :, 0], pts[:, None, 1] - taken[None, :, 1]), axis=1)
            if taken.size
            else np.full(len(pts), 1e9)
        )
        d = d + rng.random(len(d))  # deterministic tie-break
        i = int(np.argmax(d))
        chosen.append(int(cand[i]))
        taken = np.vstack([taken, pts[i]])
    return [
        {
            "id": f"node_{c}",
            "name": f"Junction {i + 1} ({float(g.lat[c]):.4f}, {float(g.lon[c]):.4f})",
            "lat": float(g.lat[c]),
            "lon": float(g.lon[c]),
            "x": float(g.x[c]),
            "z": float(g.z[c]),
            "node": int(c),
            "kind": "junction",
        }
        for i, c in enumerate(chosen)
    ]


def _pairs(places: list[dict[str, Any]], lo: float, hi: float) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    out = []
    for a, b in itertools.permutations(places, 2):
        d = math.hypot(a["x"] - b["x"], a["z"] - b["z"])
        if lo <= d <= hi:
            out.append((a, b))
    return out


def run_search(
    ctx: CityContext,
    places: list[dict[str, Any]],
    lo: float,
    hi: float,
    departs: tuple[str, ...],
    dates: tuple[str, ...],
    modes: tuple[str, ...],
    serial: bool = False,
    workers: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    pairs = _pairs(places, lo, hi)
    skipped_dates = [d for d in dates if not ctx.has_exposure(d)]
    dates = tuple(d for d in dates if d not in skipped_dates)
    jobs = []
    for a, b in pairs:
        for mode in modes:
            if mode == "cycle" and a["id"] > b["id"]:
                continue  # cycling: one direction per pair keeps the search affordable
            for dt in dates:
                for hh in departs:
                    jobs.append((a, b, mode, dt, hh))
    t0 = time.perf_counter()
    rows: list[dict[str, Any] | None]
    if serial or len(jobs) < 40:
        rows = [eval_pair(ctx, *j) for j in jobs]
    else:
        n = workers or max(1, min(8, (os.cpu_count() or 2) - 1))
        with ProcessPoolExecutor(
            n, initializer=_init_worker, initargs=(ctx.city_id, os.environ.get("ZILL_CITIES_DIR"))
        ) as ex:
            rows = list(ex.map(_eval_job, jobs, chunksize=8))
    good = [r for r in rows if r is not None]
    info = {
        "places": len(places),
        "pairs_in_band": len(pairs),
        "band_m": [lo, hi],
        "jobs": len(jobs),
        "routed": len(good),
        "unroutable": len(rows) - len(good),
        "elapsed_s": round(time.perf_counter() - t0, 1),
        "departs": list(departs),
        "dates": list(dates),
        "modes": list(modes),
        "skipped_dates_no_exposure": skipped_dates,
    }
    return good, info


def _rank(rows: list[dict[str, Any]], **flt: Any) -> list[dict[str, Any]]:
    out = [r for r in rows if r["eligible"] and all(r.get(k) == v for k, v in flt.items())]
    out.sort(key=lambda r: (-r["sun_saved_s"], r["added_time_s"]))
    return out


def select(rows: list[dict[str, Any]], date_id: str = "summer") -> dict[str, dict[str, Any] | None]:
    tourist_pool = _rank(rows, mode="walk", date_id=date_id)
    tourist = tourist_pool[0] if tourist_pool else None
    if tourist:
        # prefer an AC / covered route when it is nearly as good (PRD 8.6.3)
        ac = [r for r in tourist_pool if r["coolest_indoor_pct"] + r["coolest_covered_pct"] > 0]
        if ac and ac[0]["sun_saved_s"] >= 0.8 * tourist["sun_saved_s"]:
            tourist = ac[0]
    used = {(tourist["origin"], tourist["dest"])} if tourist else set()
    rider_pool = [
        r for r in _rank(rows, mode="cycle", date_id=date_id) if (r["origin"], r["dest"]) not in used
    ]
    rider = rider_pool[0] if rider_pool else None
    if rider:
        used.add((rider["origin"], rider["dest"]))
    crew_pool = [
        r
        for r in _rank(rows, mode="walk", date_id=date_id)
        if r["straight_m"] <= CREW_MAX_STRAIGHT_M and (r["origin"], r["dest"]) not in used
    ]
    # short + high exposure: weight the saving by how sun-exposed the fastest route is
    crew_pool.sort(
        key=lambda r: -(r["sun_saved_s"] * (r["fastest_sun_s"] / max(r["fastest_duration_s"], 1.0)))
    )
    return {
        "tourist_walk": tourist,
        "rider_cycle": rider,
        "crew_shuttle": crew_pool[0] if crew_pool else None,
    }


def _full(
    ctx: CityContext, row: dict[str, Any], persona: str, sid: str, with_departure: bool
) -> dict[str, Any]:
    mode, date_id, hh = row["mode"], row["date_id"], row["depart"]
    a = ctx.resolve_place(
        {"poi": row["origin"]} if ctx.poi(row["origin"]) else {"node": int(row["origin"][5:])}, mode
    )
    b = ctx.resolve_place(
        {"poi": row["dest"]} if ctx.poi(row["dest"]) else {"node": int(row["dest"][5:])}, mode
    )
    dep = ctx.at(date_id, hh)
    res = tdsp.compare(ctx, a["node"], b["node"], mode, dep, date_id, with_geometry=True)

    def pl(p: dict[str, Any], name: str) -> dict[str, Any]:
        return {"name": name, "lat": p["lat"], "lon": p["lon"], "node": p["node"], "x": p["x"], "z": p["z"]}

    out: dict[str, Any] = {
        "id": sid,
        "persona": persona,
        "mode": mode,
        "origin": pl(a, row["origin_name"]),
        "dest": pl(b, row["dest_name"]),
        "date_id": date_id,
        "depart": hh,
        "fastest": res["fastest"].to_dict(),
        "coolest": res["coolest"].to_dict(),
        "balanced": res["balanced"].to_dict(),
        "departure": None,
    }
    if with_departure:
        d = optimise_departure(
            ctx, a["node"], b["node"], mode, dep, dep + timedelta(minutes=90), date_key=date_id
        )
        out["departure"] = d.to_dict()
    return out


def generate(
    city_id: str = config.DEFAULT_CITY, out_path: Path | None = None, serial: bool = False, log: Any = print
) -> dict[str, Any]:
    ctx = get_city(city_id)
    places = _places(ctx)
    attempts: list[dict[str, Any]] = []

    def attempt(name: str, pl: list[dict[str, Any]], lo: float, hi: float, departs: tuple[str, ...]):
        rows, info = run_search(ctx, pl, lo, hi, departs, DATES, ("walk", "cycle"), serial)
        sel = select(rows)
        best_t = sel["tourist_walk"]["sun_saved_s"] if sel["tourist_walk"] else 0.0
        info.update(
            name=name,
            eligible=sum(1 for r in rows if r["eligible"]),
            best_tourist_sun_saved_s=best_t,
            selected={
                k: (None if v is None else f"{v['origin']}->{v['dest']} {v['mode']} {v['depart']}")
                for k, v in sel.items()
            },
        )
        attempts.append(info)
        log(
            f"[scenarios] {name}: {info['jobs']} jobs in {info['elapsed_s']}s, eligible {info['eligible']}, "
            f"best tourist sun_saved_s {best_t:.1f}"
        )
        return rows, sel

    rows, sel = attempt("baseline: gazetteer pairs 400-1500 m", places, 400.0, 1500.0, DEPARTS)
    best = sel["tourist_walk"]["sun_saved_s"] if sel["tourist_walk"] else 0.0
    all_rows = list(rows)
    if best < MIN_TOURIST_SAVE_S:
        extra = _graph_places(ctx, 12, places)
        wider = places + extra
        deps2 = ("11:30", "12:00", "12:30", "13:00", "13:30", "14:00", "14:30", "15:00", "15:30", "16:00")
        rows2, sel2 = attempt(
            "widened: +12 graph junctions, band 300-2000 m, 10 departures", wider, 300.0, 2000.0, deps2
        )
        all_rows = rows2 + [r for r in rows if r not in rows2]
        sel = select(all_rows)
    scen = []
    notes = []
    for sid, persona in (("tourist_walk", "tourist"), ("rider_cycle", "rider"), ("crew_shuttle", "crew")):
        row = sel.get(sid)
        if row is None:
            notes.append(f"{sid}: no eligible candidate found")
            continue
        scen.append(_full(ctx, row, persona, sid, with_departure=(sid == "tourist_walk")))
    tour = sel["tourist_walk"]
    if tour is None or tour["sun_saved_s"] < MIN_TOURIST_SAVE_S:
        notes.append(
            f"Best tourist sun_saved_s is below the {MIN_TOURIST_SAVE_S:.0f} s threshold even after "
            "widening; the Film must present this honestly (lean on the departure optimiser and AC links)."
        )
    ranked = sorted([r for r in all_rows if r["eligible"]], key=lambda r: -r["sun_saved_s"])[:20]
    out = {
        "generated_at": datetime.now(ZoneInfo(ctx.tz)).isoformat(timespec="seconds"),
        "city": city_id,
        "search": {
            "procedure": "PRD 8.6: all place pairs 400-1500 m apart x departures x {summer, hackathon} x "
            "walk (+cycle); "
            f"rank by sun_saved_s with added_time <= {MAX_ADDED_FRAC:.0%} of fastest and "
            f"detour <= {MAX_DETOUR}",
            "attempts": attempts,
            "notes": notes,
            "min_tourist_sun_saved_s": MIN_TOURIST_SAVE_S,
            "lambdas": config.LAMBDAS,
            "model": "Model v1: buildings, mapped trees, covered links",
        },
        "scenarios": scen,
        "candidates": ranked,
    }
    path = out_path or (
        config.DATA_DIR
        / "scenarios"
        / ("hero.json" if city_id == config.DEFAULT_CITY else f"hero_{city_id}.json")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    log(f"[scenarios] wrote {path}")
    return out


def headline(out: dict[str, Any]) -> list[str]:
    lines = []
    for s in out["scenarios"]:
        f, c = s["fastest"]["stats"], s["coolest"]["stats"]
        lines.append(
            f"{s['id']}: {s['origin']['name']} -> {s['dest']['name']} {s['mode']} {s['date_id']} "
            f"{s['depart']}  "
            f"fastest {f['duration_s']:.0f}s/{f['sun_exposure_s']:.0f}s sun | coolest {c['duration_s']:.0f}s/"
            f"{c['sun_exposure_s']:.0f}s sun | saved {c['sun_saved_s']:.0f}s ({c['sun_saved_pct']:.0f}%), "
            f"+{c['added_time_s']:.0f}s, rhl -{c['rhl_saved_pct']:.0f}%"
        )
    return lines


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default=config.DEFAULT_CITY)
    ap.add_argument("--out", default=None)
    ap.add_argument("--serial", action="store_true")
    a = ap.parse_args()
    res = generate(a.city, Path(a.out) if a.out else None, a.serial)
    print("\n".join(headline(res)))

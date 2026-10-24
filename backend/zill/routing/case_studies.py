"""Film case studies: four personas, real engine numbers, each chosen by a short documented SEARCH.

    python -m zill.routing.case_studies [--out data/scenarios/case_studies.json] [--serial]

Nothing here is hand-tuned: every case is the top row of a fixed search (method + inputs recorded in
the JSON), using the same filters as `zill.routing.scenarios` (network ratio <= 1.6, added time <= 25 %
of fastest, detour <= 1.35, a real sun saving / gain). Pairs whose endpoints are both curated places are
preferred when that tier reaches the tier threshold (as in scenarios.py).

a  hotel_guest      Dubai, shade, walk. Origins = places of kind hotel; destinations = landmark | mall |
                    park | water; straight line 800-1500 m; summer (2026-07-15) 14:00 / 15:00 / 16:00.
                    Rank by sun_saved_s.
b  delivery_rider   Dubai, shade, cycle. All place pairs 400-1500 m (the hero band, one direction per
                    pair); summer 14:00. Rank by sun_saved_s. Per-shift line = N x per-trip saving,
                    with N an explicit ASSUMPTION (not a measurement).
c  winter_daylight  Oslo, sun, walk, 2026-12-21: reused verbatim from hero_oslo.json
                    (solstice_midday_walk, its own documented search S8).
d1 run_dubai_dawn   Dubai, shade, run. Loop = A->B then B->A (two route calls; the return leg departs at
                    the outbound arrival time). Legs 1500-2600 m straight; loop fastest distance
                    4-6 km; summer 06:00 / 06:30. Rank by loop sun_saved_s.
d2 run_oslo_lunch   Oslo, sun, run. Same loop procedure; winter (2026-12-21) 11:30-13:00 every 30 min.
                    Rank by loop sun_gained_s.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from zill import config
from zill.routing import scenarios as S
from zill.routing import tdsp
from zill.routing.graph import NoRoute
from zill.services import CityContext, get_city

HOTEL_DEST_KINDS = {"landmark", "mall", "park", "water"}
HOTEL_BAND_M = (800.0, 1500.0)
HOTEL_DEPARTS = ("14:00", "15:00", "16:00")
RIDER_BAND_M = (400.0, 1500.0)
RIDER_DEPARTS = ("14:00",)
RIDER_TRIPS_ASSUMPTION = 10  # ASSUMPTION for the per-shift line only; not measured, not a customer figure
RUN_LEG_BAND_M = (1500.0, 2600.0)
RUN_LOOP_DIST_M = (4000.0, 6000.0)
RUN_MAX_LEG_S = 20 * 60.0
DUBAI_RUN_DEPARTS = ("06:00", "06:30")
OSLO_RUN_DEPARTS = ("11:30", "12:00", "12:30", "13:00")
TIER1_MIN_S = 60.0

PROCEDURE = __doc__.split("\n\n", 2)[2].strip()


# ---------------------------------------------------------------------------------------------
# loop evaluation (run)
# ---------------------------------------------------------------------------------------------
def _best_key(preference: str) -> str:
    return "sunniest" if preference == "sun" else "coolest"


def loop_routes(
    ctx: CityContext,
    a_node: int,
    b_node: int,
    mode: str,
    dep: datetime,
    date_id: str,
    preference: str,
    with_geometry: bool = False,
) -> dict[str, tuple[tdsp.RouteResult, tdsp.RouteResult]]:
    """{"fastest": (out, back), "best": (out, back)}; each return leg departs at its outbound arrival."""
    key = _best_key(preference)
    out = tdsp.compare(
        ctx, a_node, b_node, mode, dep, date_id, with_geometry=with_geometry, preference=preference
    )
    f_out, b_out = out["fastest"], out[key]
    f_back = tdsp.compare(
        ctx,
        b_node,
        a_node,
        mode,
        dep + timedelta(seconds=f_out.stats["duration_s"]),
        date_id,
        with_geometry=with_geometry,
        preference=preference,
    )["fastest"]
    b_back = tdsp.compare(
        ctx,
        b_node,
        a_node,
        mode,
        dep + timedelta(seconds=b_out.stats["duration_s"]),
        date_id,
        with_geometry=with_geometry,
        preference=preference,
    )[key]
    return {"fastest": (f_out, f_back), "best": (b_out, b_back)}


def _sum(legs: tuple[tdsp.RouteResult, tdsp.RouteResult]) -> dict[str, float]:
    return {
        k: round(sum(float(r.stats[k]) for r in legs), 2)
        for k in ("distance_m", "duration_s", "sun_exposure_s", "rhl")
    }


def eval_loop(
    ctx: CityContext,
    a: dict[str, Any],
    b: dict[str, Any],
    mode: str,
    date_id: str,
    hhmm: str,
    preference: str,
) -> dict[str, Any] | None:
    try:
        lr = loop_routes(
            ctx, a["nodes"]["walk"], b["nodes"]["walk"], mode, ctx.at(date_id, hhmm), date_id, preference
        )
    except NoRoute:
        return None
    f, c = _sum(lr["fastest"]), _sum(lr["best"])
    straight = math.hypot(a["x"] - b["x"], a["z"] - b["z"])
    ratio = max(r.stats["distance_m"] for r in lr["fastest"]) / straight if straight > 0 else 99.0
    added = c["duration_s"] - f["duration_s"]
    added_frac = added / f["duration_s"] if f["duration_s"] > 0 else 0.0
    detour = c["distance_m"] / f["distance_m"] if f["distance_m"] > 0 else 1.0
    delta = (
        (c["sun_exposure_s"] - f["sun_exposure_s"])
        if preference == "sun"
        else (f["sun_exposure_s"] - c["sun_exposure_s"])
    )
    reject = None
    if ratio > S.MAX_NETWORK_RATIO:
        reject = "network_ratio>1.6"
    elif not (RUN_LOOP_DIST_M[0] <= f["distance_m"] <= RUN_LOOP_DIST_M[1]):
        reject = "loop_distance_outside_4-6km"
    elif max(r.stats["duration_s"] for r in lr["fastest"]) > RUN_MAX_LEG_S:
        reject = "leg_duration>20min"
    elif delta <= 0:
        reject = "no_sun_gained" if preference == "sun" else "no_sun_saved"
    elif added_frac > S.MAX_ADDED_FRAC:
        reject = "added_time>25%"
    elif detour > S.MAX_DETOUR:
        reject = "detour>1.35"
    return {
        "origin": a["id"],
        "dest": b["id"],
        "origin_name": a["name"],
        "dest_name": b["name"],
        "mode": mode,
        "date_id": date_id,
        "depart": hhmm,
        "preference": preference,
        "straight_m": round(straight, 1),
        "network_ratio": round(ratio, 3),
        "fastest": f,
        "best": c,
        "delta_sun_s": round(delta, 2),
        "added_time_s": round(added, 2),
        "added_frac": round(added_frac, 4),
        "detour_ratio": round(detour, 4),
        "both_curated": bool(a.get("curated") and b.get("curated")),
        "reject": reject,
        "eligible": reject is None,
    }


# ---------------------------------------------------------------------------------------------
# parallel job runner (reuses the scenarios.py worker context)
# ---------------------------------------------------------------------------------------------
def _job(job: tuple) -> dict[str, Any] | None:
    ctx = S._WORKER_CTX
    assert ctx is not None
    return _run_job(ctx, job)


def _run_job(ctx: CityContext, job: tuple) -> dict[str, Any] | None:
    kind, a, b, mode, date_id, hh, pref = job
    if kind == "loop":
        return eval_loop(ctx, a, b, mode, date_id, hh, pref)
    return S.eval_pair(ctx, a, b, mode, date_id, hh)


def run_jobs(
    ctx: CityContext, jobs: list[tuple], serial: bool
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    t0 = time.perf_counter()
    if serial or len(jobs) < 40:
        rows = [_run_job(ctx, j) for j in jobs]
    else:
        n = max(1, min(8, (os.cpu_count() or 2) - 1))
        with ProcessPoolExecutor(
            n, initializer=S._init_worker, initargs=(ctx.city_id, os.environ.get("ZILL_CITIES_DIR"))
        ) as ex:
            rows = list(ex.map(_job, jobs, chunksize=4))
    good = [r for r in rows if r is not None]
    info = {
        "jobs": len(jobs),
        "routed": len(good),
        "unroutable": len(rows) - len(good),
        "eligible": sum(1 for r in good if r["eligible"]),
        "rejections_first_failing_filter": dict(Counter(r["reject"] for r in good if r["reject"])),
        "elapsed_s": round(time.perf_counter() - t0, 1),
    }
    return good, info


def rank(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    out = [r for r in rows if r["eligible"]]
    out.sort(key=lambda r: (-r[key], r["added_time_s"], r["origin"], r["dest"], r["depart"]))
    t1 = [r for r in out if r.get("both_curated")]
    return t1 if t1 and t1[0][key] >= TIER1_MIN_S else out


def _pairs(
    places: list[dict[str, Any]], lo: float, hi: float, origin_ok: Any = None, dest_ok: Any = None
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    out = []
    for a, b in itertools.permutations(places, 2):
        if origin_ok and not origin_ok(a):
            continue
        if dest_ok and not dest_ok(b):
            continue
        if lo <= math.hypot(a["x"] - b["x"], a["z"] - b["z"]) <= hi:
            out.append((a, b))
    return out


# ---------------------------------------------------------------------------------------------
# output blocks
# ---------------------------------------------------------------------------------------------
def _side(stats: dict[str, Any]) -> dict[str, Any]:
    return {
        "duration_s": round(float(stats["duration_s"]), 1),
        "duration_min": round(float(stats["duration_s"]) / 60.0, 1),
        "direct_sun_s": round(float(stats["sun_exposure_s"]), 1),
        "direct_sun_min": round(float(stats["sun_exposure_s"]) / 60.0, 1),
        "distance_m": round(float(stats["distance_m"]), 1),
    }


def _delta(f: dict[str, Any], b: dict[str, Any], preference: str) -> dict[str, Any]:
    d = {
        "added_time_s": round(b["duration_s"] - f["duration_s"], 1),
        "added_time_min": round((b["duration_s"] - f["duration_s"]) / 60.0, 1),
        "added_distance_m": round(b["distance_m"] - f["distance_m"], 1),
    }
    if preference == "sun":
        g = b["direct_sun_s"] - f["direct_sun_s"]
        d.update({"sun_gained_s": round(g, 1), "sun_gained_min": round(g / 60.0, 1)})
        if f["direct_sun_s"] > 0:
            d["sun_gained_pct"] = round(100.0 * g / f["direct_sun_s"], 1)
    else:
        s = f["direct_sun_s"] - b["direct_sun_s"]
        d.update({"sun_saved_s": round(s, 1), "sun_saved_min": round(s / 60.0, 1)})
        if f["direct_sun_s"] > 0:
            d["sun_saved_pct"] = round(100.0 * s / f["direct_sun_s"], 1)
    return d


def _wellbeing(
    ctx: CityContext, dep: datetime, preference: str, stats: dict[str, Any], segments: list[dict[str, Any]]
) -> dict[str, Any]:
    from zill import weather, wellbeing
    from zill.sun.position import sun_position

    alt = sun_position(dep, ctx.origin["lat"], ctx.origin["lon"], ctx.tz).alt_deg
    w = weather.get(ctx.city_id, dep, allow_live=False, prefer_recorded=True)
    w.pop("hourly", None)
    wb = wellbeing.assess(preference, alt, w, stats, segments)
    return {
        "uv_index": wb["uv"].get("index"),
        "uv_band": wb["uv"].get("band"),
        "sun_altitude_deg": round(float(alt), 1),
        "daylight_window": wb["daylight_window"],
        "heat_stress": wb["heat_stress"],
        "weather_source": wb["weather"].get("source"),
        "weather_label": wb["weather"].get("label"),
        "weather": wb["weather"],
        "disclaimer": wb["disclaimer"],
    }


def _place(ctx: CityContext, pid: str, name: str, mode: str) -> dict[str, Any]:
    p = ctx.resolve_place({"poi": pid}, "walk" if mode == "run" else mode)
    return {"id": pid, "name": name, "lat": p["lat"], "lon": p["lon"], "node": p["node"]}


def build_pair_case(
    ctx: CityContext, row: dict[str, Any], cid: str, label: str, persona: str, method: dict[str, Any]
) -> dict[str, Any]:
    mode, date_id, hh = row["mode"], row["date_id"], row["depart"]
    o, d = (
        _place(ctx, row["origin"], row["origin_name"], mode),
        _place(ctx, row["dest"], row["dest_name"], mode),
    )
    dep = ctx.at(date_id, hh)
    res = tdsp.compare(ctx, o["node"], d["node"], mode, dep, date_id, with_geometry=True)
    f, b = res["fastest"], res["coolest"]
    fs, bs = _side(f.stats), _side(b.stats)
    return {
        "id": cid,
        "label": label,
        "persona": persona,
        "city": ctx.city_id,
        "date": dep.date().isoformat(),
        "date_id": date_id,
        "depart": hh,
        "depart_iso": dep.isoformat(),
        "origin": o,
        "dest": d,
        "mode": mode,
        "preference": "shade",
        "route_shape": "A->B",
        "fastest": {**fs, "edges": f.edges},
        "best": {**bs, "label": "coolest", "edges": b.edges, "note": b.stats.get("note")},
        "delta": _delta(fs, bs, "shade"),
        "wellbeing": _wellbeing(ctx, dep, "shade", b.stats, b.segments),
        "method": method,
    }


def build_loop_case(
    ctx: CityContext, row: dict[str, Any], cid: str, label: str, persona: str, method: dict[str, Any]
) -> dict[str, Any]:
    mode, date_id, hh, pref = row["mode"], row["date_id"], row["depart"], row["preference"]
    o, d = (
        _place(ctx, row["origin"], row["origin_name"], mode),
        _place(ctx, row["dest"], row["dest_name"], mode),
    )
    dep = ctx.at(date_id, hh)
    lr = loop_routes(ctx, o["node"], d["node"], mode, dep, date_id, pref, with_geometry=True)

    def side(legs: tuple[tdsp.RouteResult, tdsp.RouteResult]) -> dict[str, Any]:
        tot = _sum(legs)
        return {
            **_side(tot),
            "legs": [
                {"leg": name, "depart_iso": r.depart.isoformat(), **_side(r.stats), "edges": r.edges}
                for name, r in zip(("out A->B", "back B->A"), legs, strict=True)
            ],
        }

    fs, bs = side(lr["fastest"]), side(lr["best"])
    bsum = _sum(lr["best"])
    segs = [s for r in lr["best"] for s in r.segments]
    return {
        "id": cid,
        "label": label,
        "persona": persona,
        "city": ctx.city_id,
        "date": dep.date().isoformat(),
        "date_id": date_id,
        "depart": hh,
        "depart_iso": dep.isoformat(),
        "origin": o,
        "dest": d,
        "turnaround": d["name"],
        "mode": mode,
        "pace": {
            "speed_m_s": config.SPEEDS[mode],
            "min_per_km": round(1000.0 / config.SPEEDS[mode] / 60.0, 2),
        },
        "preference": pref,
        "route_shape": "loop A->B->A as two route calls; the return leg departs at the outbound arrival",
        "fastest": fs,
        "best": {**bs, "label": _best_key(pref)},
        "delta": _delta(_side(_sum(lr["fastest"])), _side(bsum), pref),
        "wellbeing": _wellbeing(ctx, dep, pref, bsum, segs),
        "method": method,
    }


def oslo_winter_case() -> dict[str, Any] | None:
    src = config.DATA_DIR / "scenarios" / "hero_oslo.json"
    try:
        blk = json.loads(src.read_text(encoding="utf-8"))["sun"]
    except Exception:
        return None
    s = next((x for x in blk.get("scenarios", []) if x and x.get("id") == "solstice_midday_walk"), None)
    if s is None:
        return None
    ctx = get_city("oslo")
    dep = ctx.at(s["date_id"], s["depart"])
    fs, bs = _side(s["fastest"]["stats"]), _side(s["sunniest"]["stats"])
    wb = s["wellbeing"]
    return {
        "id": "winter_daylight",
        "label": "Winter daylight",
        "persona": "daylight_seeker",
        "city": "oslo",
        "date": dep.date().isoformat(),
        "date_id": s["date_id"],
        "depart": s["depart"],
        "depart_iso": dep.isoformat(),
        "origin": {k: s["origin"][k] for k in ("name", "lat", "lon", "node")},
        "dest": {k: s["dest"][k] for k in ("name", "lat", "lon", "node")},
        "mode": s["mode"],
        "preference": "sun",
        "route_shape": "A->B",
        "fastest": {**fs, "edges": s["fastest"]["edges"]},
        "best": {**bs, "label": "sunniest", "edges": s["sunniest"]["edges"]},
        "delta": _delta(fs, bs, "sun"),
        "wellbeing": {
            "uv_index": wb["uv"].get("index"),
            "uv_band": wb["uv"].get("band"),
            "sun_altitude_deg": wb["daylight_window"].get("sun_alt_deg"),
            "daylight_window": wb["daylight_window"],
            "heat_stress": wb["heat_stress"],
            "weather_source": wb["weather"].get("source"),
            "weather_label": wb["weather"].get("label"),
            "weather": wb["weather"],
            "disclaimer": wb["disclaimer"],
        },
        "method": {
            "reused_from": "data/scenarios/hero_oslo.json sun.scenarios[solstice_midday_walk]",
            "search": "scenarios.py S8 (Oslo winter, departures 11:30-13:00, fastest vs sunniest, ranked by "
            "sun_gained_s); numbers copied verbatim, not re-tuned",
            "generated_at": blk.get("generated_at"),
        },
    }


# ---------------------------------------------------------------------------------------------
def generate(serial: bool = False, log: Any = print) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    notes: list[str] = []
    dubai = get_city("dubai_downtown")
    dplaces, dfilter = S._places(dubai)

    # a: hotel guest
    pairs = _pairs(
        dplaces,
        *HOTEL_BAND_M,
        origin_ok=lambda p: p["kind"] == "hotel",
        dest_ok=lambda p: p["kind"] in HOTEL_DEST_KINDS,
    )
    jobs = [("pair", a, b, "walk", "summer", hh, "shade") for a, b in pairs for hh in HOTEL_DEPARTS]
    rows, info = run_jobs(dubai, jobs, serial)
    log(f"hotel: {len(pairs)} pairs, {info}")
    top = rank(rows, "sun_saved_s")
    meth = {
        "procedure": "a (see procedure)",
        "inputs": {
            "origins": "places of kind hotel",
            "dest_kinds": sorted(HOTEL_DEST_KINDS),
            "band_m": list(HOTEL_BAND_M),
            "departs": list(HOTEL_DEPARTS),
            "date_id": "summer",
        },
        "pairs": len(pairs),
        **info,
        "runner_up": [_brief(r, "sun_saved_s") for r in top[1:4]],
    }
    if top:
        cases.append(build_pair_case(dubai, top[0], "hotel_guest", "Hotel guest", "tourist", meth))
    else:
        notes.append("hotel_guest: no eligible row")

    # b: delivery rider
    pairs = [
        (a, b) for a, b in _pairs(dplaces, *RIDER_BAND_M) if "cycle" in a["nodes"] and "cycle" in b["nodes"]
    ]
    pairs = [(a, b) for a, b in pairs if a["id"] < b["id"]]  # one direction per pair (as scenarios.py)
    jobs = [("pair", a, b, "cycle", "summer", hh, "shade") for a, b in pairs for hh in RIDER_DEPARTS]
    rows, info = run_jobs(dubai, jobs, serial)
    log(f"rider: {len(pairs)} pairs, {info}")
    top = rank(rows, "sun_saved_s")
    meth = {
        "procedure": "b (see procedure)",
        "inputs": {
            "band_m": list(RIDER_BAND_M),
            "departs": list(RIDER_DEPARTS),
            "date_id": "summer",
            "mode": "cycle",
        },
        "pairs": len(pairs),
        **info,
        "runner_up": [_brief(r, "sun_saved_s") for r in top[1:4]],
        "hero_rider_cycle": "hero.json rider_cycle (Maryland International Hotel -> Taj Dubai Hotel, 15:30) "
        "is "
        "unchanged; this case is the same search procedure at the July 14:00 departure",
    }
    if top:
        c = build_pair_case(dubai, top[0], "delivery_rider", "Delivery rider", "rider", meth)
        n = RIDER_TRIPS_ASSUMPTION
        c["per_shift"] = {
            "assumption": (
                f"ASSUMPTION: a rider does {n} trips like this one in a shift (illustrative, not measured)"
            ),
            "trips": n,
            "is_assumption": True,
            "sun_saved_min": round(n * c["delta"]["sun_saved_s"] / 60.0, 1),
            "added_time_min": round(n * c["delta"]["added_time_s"] / 60.0, 1),
            "arithmetic": "trips x per-trip engine delta; every real trip differs",
        }
        cases.append(c)
    else:
        notes.append("delivery_rider: no eligible row")

    # c: winter daylight (reuse)
    c = oslo_winter_case()
    if c:
        cases.append(c)
    else:
        notes.append("winter_daylight: hero_oslo.json solstice_midday_walk missing")

    # d1: Dubai dawn run (shade)
    pairs = _pairs(dplaces, *RUN_LEG_BAND_M)
    pairs = [(a, b) for a, b in pairs if a["id"] < b["id"]]  # a loop covers both directions
    jobs = [("loop", a, b, "run", "summer", hh, "shade") for a, b in pairs for hh in DUBAI_RUN_DEPARTS]
    rows, info = run_jobs(dubai, jobs, serial)
    log(f"run dubai: {len(pairs)} pairs, {info}")
    top = rank(rows, "delta_sun_s")
    meth = {
        "procedure": "d1 (see procedure)",
        "inputs": {
            "leg_band_m": list(RUN_LEG_BAND_M),
            "loop_fastest_distance_m": list(RUN_LOOP_DIST_M),
            "max_leg_s": RUN_MAX_LEG_S,
            "departs": list(DUBAI_RUN_DEPARTS),
            "date_id": "summer",
            "speed_m_s": config.SPEEDS["run"],
        },
        "pairs": len(pairs),
        **info,
        "runner_up": [_brief(r, "delta_sun_s") for r in top[1:4]],
    }
    if top:
        cases.append(
            build_loop_case(dubai, top[0], "run_dubai_dawn", "Running club: Dubai dawn", "runner", meth)
        )
    else:
        notes.append("run_dubai_dawn: no eligible loop")

    # d2: Oslo winter lunchtime run (sun)
    oslo = get_city("oslo")
    oplaces, ofilter = S._places(oslo)
    pairs = [(a, b) for a, b in _pairs(oplaces, *RUN_LEG_BAND_M) if a["id"] < b["id"]]
    jobs = [("loop", a, b, "run", "winter", hh, "sun") for a, b in pairs for hh in OSLO_RUN_DEPARTS]
    rows, info = run_jobs(oslo, jobs, serial)
    log(f"run oslo: {len(pairs)} pairs, {info}")
    top = rank(rows, "delta_sun_s")
    meth = {
        "procedure": "d2 (see procedure)",
        "inputs": {
            "leg_band_m": list(RUN_LEG_BAND_M),
            "loop_fastest_distance_m": list(RUN_LOOP_DIST_M),
            "max_leg_s": RUN_MAX_LEG_S,
            "departs": list(OSLO_RUN_DEPARTS),
            "date_id": "winter",
            "speed_m_s": config.SPEEDS["run"],
        },
        "pairs": len(pairs),
        **info,
        "runner_up": [_brief(r, "delta_sun_s") for r in top[1:4]],
    }
    if top:
        cases.append(
            build_loop_case(oslo, top[0], "run_oslo_lunch", "Running club: Oslo winter lunch", "runner", meth)
        )
    else:
        notes.append("run_oslo_lunch: no eligible loop")

    return {
        "generated_at": datetime.now(ZoneInfo(config.TIMEZONE)).isoformat(timespec="seconds"),
        "generator": "python -m zill.routing.case_studies",
        "procedure": PROCEDURE,
        "filters": {
            "max_network_ratio": S.MAX_NETWORK_RATIO,
            "max_added_frac": S.MAX_ADDED_FRAC,
            "max_detour": S.MAX_DETOUR,
            "walk_max_duration_s": S.MAX_DURATION_S["walk"],
            "cycle_max_duration_s": S.MAX_DURATION_S["cycle"],
            "tier1_both_curated_min_s": TIER1_MIN_S,
        },
        "place_filter": {"dubai_downtown": dfilter, "oslo": ofilter},
        "labels": {
            "weather": (
                "Recorded weather (Open-Meteo archive / cache) for each date; see wellbeing.weather_label"
            ),
            "run_pace": "2.8 m/s (about 6:00 min/km) is an assumed recreational pace (config.SPEEDS['run'])",
        },
        "cases": cases,
        "notes": notes,
    }


def _brief(r: dict[str, Any], key: str) -> dict[str, Any]:
    return {"origin": r["origin_name"], "dest": r["dest_name"], "depart": r["depart"], key: r[key]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(config.DATA_DIR / "scenarios" / "case_studies.json"))
    ap.add_argument("--serial", action="store_true")
    args = ap.parse_args()
    out = generate(args.serial)
    Path(args.out).write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    for c in out["cases"]:
        print(
            c["id"],
            c["origin"]["name"],
            "->",
            c["dest"]["name"],
            c["depart"],
            c["fastest"]["duration_min"],
            c["fastest"]["direct_sun_min"],
            "|",
            c["best"]["duration_min"],
            c["best"]["direct_sun_min"],
            c["delta"],
        )
    print("notes:", out["notes"])


if __name__ == "__main__":
    main()

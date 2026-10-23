"""Hero scenario auto-selection (PRD 8.6): a documented SEARCH, never hand-picked, never fabricated.

    python -m zill.routing.scenarios --city dubai_downtown [--out data/scenarios/hero.json] [--serial]

Procedure
1. Candidate places: curated gazetteer / OSM POIs of kind landmark|mall|hotel|metro|park|water that snap
   to the mode's network within SNAP_MAX_M (no cafe / restaurant / shop-level POIs).
2. All ordered place pairs 400-1500 m apart x departures {12:30,13:30,14:30,15:30} x {summer, hackathon}
   x walk (+cycle) are routed Fastest vs Coolest.
3. Row filters (each rejection is counted in hero.json["search"]): network sanity (fastest distance /
   straight line <= 1.6), duration caps (walk <= 25 min, cycle <= 15 min), PRD ranking constraints
   (added_time <= 25% of fastest, detour coolest/fastest distance <= 1.35, sun actually saved).
4. Rank by sun_saved_s. tourist_walk prefers a coolest route that uses AC / covered / indoor edges when
   it is within 85% of the best saving; crew_shuttle = straight line <= 700 m and fastest walk <= 12 min,
   weighted by how sun-exposed the fastest route is.
5. If the best tourist saving is < 90 s, the search is widened (distance band, more departures) and every
   attempt is logged.

Sun-mode procedure (`--sun`, written under hero.json["sun"]; shade entries are never touched)
S1. Same candidate places, same pair band (400-1500 m), walk only, date winter (2026-01-15).
S2. Departures: winter morning 09:00-11:00 every 30 min, and office lunch 12:00-13:30 every 30 min.
S3. Fastest vs Sunniest (sun mode, lam=3). Same network / duration / added-time (<= 25 %) / detour (<= 1.35)
    filters; a row also needs sun actually gained (> 0 s).
S4. Rank by sun_gained_s (ties: less added time). winter_morning_walk = best morning row;
    office_lunch_walk = best lunch row with fastest walk <= 15 min, different pair. Pairs with both
    endpoints curated are preferred when that tier gains >= 60 s.
S5. If the best morning gain is < 90 s the band is widened to 300-1800 m and the attempt logged.
S6. Each scenario carries the well-being block computed from the RECORDED weather for that date.
S7. spring_daylight_walk: date spring (2026-04-15), departures 10:00-11:30 every 30 min. For each departure
    the daylight window is evaluated first (sun altitude at the city origin + recorded UV and sky state);
    only departures with an OPEN window are searched, same filters, ranked by sun_gained_s, pair distinct
    from the winter scenarios.
S8. Other cities use a per-city plan (SUN_CITY_PLANS): for each scenario a date and departures; when
    `open_window` is set only departures with an open daylight window are searched (as S7). Same place
    filter, pair band 400-1500 m (widened to 300-1800 m if the best gain is < 90 s), same filters and
    ranking, pairs distinct across scenarios. A closed window is reported, never tuned away.
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
from zill.routing import tdsp
from zill.routing.departure import optimise_departure
from zill.routing.graph import NoRoute, PlaceError
from zill.services import CityContext, get_city

DEPARTS = ("12:30", "13:30", "14:30", "15:30")
DATES = ("summer", "hackathon")
MAX_ADDED_FRAC = 0.25
MAX_DETOUR = 1.35
MIN_TOURIST_SAVE_S = 90.0
CREW_MAX_STRAIGHT_M = 700.0
PLACE_KINDS = {"landmark", "mall", "hotel", "metro", "park", "water"}
SNAP_MAX_M = 60.0
MAX_NETWORK_RATIO = 1.6  # fastest network distance / straight line
MAX_DURATION_S = {"walk": 25 * 60.0, "cycle": 15 * 60.0}
CREW_MAX_DURATION_S = 12 * 60.0
AC_PREFERENCE_FRAC = 0.85

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


def _eval_job_sun(job: tuple) -> dict[str, Any] | None:
    ctx = _WORKER_CTX
    assert ctx is not None
    return eval_pair_sun(ctx, *job)


def eval_pair(
    ctx: CityContext, a: dict[str, Any], b: dict[str, Any], mode: str, date_id: str, hhmm: str
) -> dict[str, Any] | None:
    try:
        res = tdsp.compare(
            ctx, a["nodes"][mode], b["nodes"][mode], mode, ctx.at(date_id, hhmm), date_id, with_geometry=False
        )
    except NoRoute:
        return None
    f, c = res["fastest"].stats, res["coolest"].stats
    straight = math.hypot(a["x"] - b["x"], a["z"] - b["z"])
    detour = c["distance_m"] / f["distance_m"] if f["distance_m"] > 0 else 1.0
    added_frac = c["added_time_s"] / f["duration_s"] if f["duration_s"] > 0 else 0.0
    ratio = f["distance_m"] / straight if straight > 0 else 99.0
    # first failing filter (for counting) in a fixed order
    reject = None
    if ratio > MAX_NETWORK_RATIO:
        reject = "network_ratio>1.6"
    elif f["duration_s"] > MAX_DURATION_S[mode]:
        reject = f"fastest_duration>{int(MAX_DURATION_S[mode] / 60)}min"
    elif c["sun_saved_s"] <= 0:
        reject = "no_sun_saved"
    elif added_frac > MAX_ADDED_FRAC:
        reject = "added_time>25%"
    elif detour > MAX_DETOUR:
        reject = "detour>1.35"
    return {
        "origin": a["id"],
        "dest": b["id"],
        "origin_name": a["name"],
        "dest_name": b["name"],
        "mode": mode,
        "date_id": date_id,
        "depart": hhmm,
        "straight_m": round(straight, 1),
        "network_ratio": round(ratio, 3),
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
        "both_curated": bool(a.get("curated") and b.get("curated")),
        "reject": reject,
        "eligible": reject is None,
    }


def eval_pair_sun(
    ctx: CityContext, a: dict[str, Any], b: dict[str, Any], mode: str, date_id: str, hhmm: str
) -> dict[str, Any] | None:
    """Sun-mode candidate row: fastest vs sunniest (lam=3, preference='sun')."""
    try:
        res = tdsp.compare(
            ctx,
            a["nodes"][mode],
            b["nodes"][mode],
            mode,
            ctx.at(date_id, hhmm),
            date_id,
            with_geometry=False,
            preference="sun",
        )
    except NoRoute:
        return None
    f, c = res["fastest"].stats, res["sunniest"].stats
    straight = math.hypot(a["x"] - b["x"], a["z"] - b["z"])
    detour = c["distance_m"] / f["distance_m"] if f["distance_m"] > 0 else 1.0
    added_frac = c["added_time_s"] / f["duration_s"] if f["duration_s"] > 0 else 0.0
    ratio = f["distance_m"] / straight if straight > 0 else 99.0
    reject = None
    if ratio > MAX_NETWORK_RATIO:
        reject = "network_ratio>1.6"
    elif f["duration_s"] > MAX_DURATION_S[mode]:
        reject = f"fastest_duration>{int(MAX_DURATION_S[mode] / 60)}min"
    elif c["sun_gained_s"] <= 0:
        reject = "no_sun_gained"
    elif added_frac > MAX_ADDED_FRAC:
        reject = "added_time>25%"
    elif detour > MAX_DETOUR:
        reject = "detour>1.35"
    return {
        "origin": a["id"],
        "dest": b["id"],
        "origin_name": a["name"],
        "dest_name": b["name"],
        "mode": mode,
        "date_id": date_id,
        "depart": hhmm,
        "straight_m": round(straight, 1),
        "network_ratio": round(ratio, 3),
        "fastest_distance_m": f["distance_m"],
        "fastest_duration_s": f["duration_s"],
        "fastest_sun_s": f["sun_exposure_s"],
        "sunniest_duration_s": c["duration_s"],
        "sunniest_sun_s": c["sun_exposure_s"],
        "sun_gained_s": c["sun_gained_s"],
        "sun_gained_pct": c["sun_gained_pct"],
        "added_time_s": c["added_time_s"],
        "added_frac": round(added_frac, 4),
        "detour_ratio": round(detour, 4),
        "both_curated": bool(a.get("curated") and b.get("curated")),
        "reject": reject,
        "eligible": reject is None,
    }


def curated_ids(city_id: str) -> set[str]:
    """Ids of the hand-checked gazetteer entries (data/curated/<city>/gazetteer.json): well-known places."""
    f = config.DATA_DIR / "curated" / city_id / "gazetteer.json"
    try:
        return {e["id"] for e in json.loads(f.read_text(encoding="utf-8"))}
    except Exception:
        return set()


def _places(ctx: CityContext) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Candidate places with a routable node per mode (snap <= SNAP_MAX_M), plus filter counts."""
    out, rej = [], Counter()
    cur = curated_ids(ctx.city_id)
    for p in ctx.pois:
        if p.get("kind") not in PLACE_KINDS:
            rej[f"kind:{p.get('kind')}"] += 1
            continue
        nodes = {}
        for mode in ("walk", "cycle"):
            try:
                r = ctx.resolve_place({"poi": p["id"]}, mode)
            except (PlaceError, KeyError, UnicodeError):
                continue
            if r["snap_m"] <= SNAP_MAX_M:
                nodes[mode] = r["node"]
        if "walk" not in nodes:
            rej["snap>60m"] += 1
            continue
        out.append(
            {
                "id": p["id"],
                "name": p["name"],
                "lat": p["lat"],
                "lon": p["lon"],
                "x": p["x"],
                "z": p["z"],
                "node": nodes["walk"],
                "nodes": nodes,
                "kind": p.get("kind"),
                "curated": p["id"] in cur,
            }
        )
    return out, {"kept": len(out), "rejected": dict(rej)}


def _pairs(places: list[dict[str, Any]], lo: float, hi: float) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    out = []
    for a, b in itertools.permutations(places, 2):
        if lo <= math.hypot(a["x"] - b["x"], a["z"] - b["z"]) <= hi:
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
    preference: str = "shade",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sun = preference == "sun"
    ev, job_fn = (eval_pair_sun, _eval_job_sun) if sun else (eval_pair, _eval_job)
    pairs = _pairs(places, lo, hi)
    skipped_dates = [d for d in dates if not ctx.has_exposure(d)]
    dates = tuple(d for d in dates if d not in skipped_dates)
    jobs = []
    for a, b in pairs:
        for mode in modes:
            if mode not in a["nodes"] or mode not in b["nodes"]:
                continue
            if mode == "cycle" and a["id"] > b["id"]:
                continue  # cycling: one direction per pair keeps the search affordable
            for dt in dates:
                for hh in departs:
                    jobs.append((a, b, mode, dt, hh))
    t0 = time.perf_counter()
    rows: list[dict[str, Any] | None]
    if serial or len(jobs) < 40:
        rows = [ev(ctx, *j) for j in jobs]
    else:
        n = workers or max(1, min(8, (os.cpu_count() or 2) - 1))
        with ProcessPoolExecutor(
            n, initializer=_init_worker, initargs=(ctx.city_id, os.environ.get("ZILL_CITIES_DIR"))
        ) as ex:
            rows = list(ex.map(job_fn, jobs, chunksize=8))
    good = [r for r in rows if r is not None]
    info = {
        "places": len(places),
        "pairs_in_band": len(pairs),
        "band_m": [lo, hi],
        "jobs": len(jobs),
        "routed": len(good),
        "unroutable": len(rows) - len(good),
        "rejections_first_failing_filter": dict(Counter(r["reject"] for r in good if r["reject"])),
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


def _tier1(pool: list[dict[str, Any]], key: Any = None, min_save_s: float = 60.0) -> list[dict[str, Any]]:
    """Prefer pairs whose endpoints are both curated places if that tier saves >= min_save_s."""
    t1 = [r for r in pool if r.get("both_curated")]
    if key:
        t1.sort(key=key)
    return t1 if t1 and t1[0]["sun_saved_s"] >= min_save_s else pool


def select(rows: list[dict[str, Any]], date_id: str = "summer") -> dict[str, dict[str, Any] | None]:
    tourist_pool = _rank(rows, mode="walk", date_id=date_id)
    # tier 1: both endpoints are curated, well-known places; fall back to all places only if that tier
    # cannot reach MIN_TOURIST_SAVE_S (honest: the fallback is recorded in `tourist_tier`)
    tier1 = [r for r in tourist_pool if r.get("both_curated")]
    if tier1 and tier1[0]["sun_saved_s"] >= MIN_TOURIST_SAVE_S:
        tourist_pool = tier1
    tourist = tourist_pool[0] if tourist_pool else None
    if tourist:
        # prefer an AC / covered / indoor coolest route when within 85% of the best saving
        ac = [r for r in tourist_pool if r["coolest_indoor_pct"] + r["coolest_covered_pct"] > 0]
        if ac and ac[0]["sun_saved_s"] >= AC_PREFERENCE_FRAC * tourist["sun_saved_s"]:
            tourist = ac[0]
    used = {frozenset((tourist["origin"], tourist["dest"]))} if tourist else set()
    rider_pool = [
        r
        for r in _rank(rows, mode="cycle", date_id=date_id)
        if frozenset((r["origin"], r["dest"])) not in used
    ]
    rider_pool = _tier1(rider_pool)
    rider = rider_pool[0] if rider_pool else None
    if rider:
        used.add(frozenset((rider["origin"], rider["dest"])))
    crew_pool = [
        r
        for r in _rank(rows, mode="walk", date_id=date_id)
        if r["straight_m"] <= CREW_MAX_STRAIGHT_M
        and r["fastest_duration_s"] <= CREW_MAX_DURATION_S
        and frozenset((r["origin"], r["dest"])) not in used
    ]
    # short + high exposure: weight the saving by how sun-exposed the fastest route is
    crew_pool = _tier1(
        crew_pool,
        key=lambda r: -(r["sun_saved_s"] * (r["fastest_sun_s"] / max(r["fastest_duration_s"], 1.0))),
    )
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
    a = ctx.resolve_place({"poi": row["origin"]}, mode)
    b = ctx.resolve_place({"poi": row["dest"]}, mode)
    dep = ctx.at(date_id, hh)
    res = tdsp.compare(ctx, a["node"], b["node"], mode, dep, date_id, with_geometry=True)

    def pl(p: dict[str, Any], name: str) -> dict[str, Any]:
        return {"name": name, "lat": p["lat"], "lon": p["lon"], "node": p["node"], "x": p["x"], "z": p["z"]}

    cool = res["coolest"]
    out: dict[str, Any] = {
        "id": sid,
        "persona": persona,
        "mode": mode,
        "origin": pl(a, row["origin_name"]),
        "dest": pl(b, row["dest_name"]),
        "date_id": date_id,
        "depart": hh,
        "straight_m": row["straight_m"],
        "uses_ac_link": any(s["cls"] == "ac_link" for s in cool.segments),
        "uses_covered": any(s["cls"] == "covered" for s in cool.segments),
        "uses_indoor": any(s["cls"] == "indoor" for s in cool.segments),
        "fastest": res["fastest"].to_dict(),
        "coolest": cool.to_dict(),
        "balanced": res["balanced"].to_dict(),
        "departure": None,
    }
    if with_departure:
        d = optimise_departure(
            ctx, a["node"], b["node"], mode, dep, dep + timedelta(minutes=90), date_key=date_id
        )
        out["departure"] = d.to_dict()
    return out


def ac_link_story(
    ctx: CityContext, a_id: str, b_id: str, date_id: str = "summer", hhmm: str = "13:30"
) -> dict[str, Any] | None:
    """Real comparison for the Metro <-> Mall story: the fastest route (free to use AC/indoor links)
    versus the fastest route without the AC link (ac_link edges blocked; indoor mall edges stay usable)."""
    if not (ctx.poi(a_id) and ctx.poi(b_id)):
        return None
    a = ctx.resolve_place({"poi": a_id}, "walk")
    b = ctx.resolve_place({"poi": b_id}, "walk")
    dep = ctx.at(date_id, hhmm)
    g = ctx.graph
    blocked = frozenset(int(i) for i, n in enumerate(g.cls_name) if n == "ac_link")
    try:
        free = tdsp.route(ctx, a["node"], b["node"], "walk", dep, 0.0, date_id, "fastest")
    except NoRoute:
        return None
    try:
        alt = tdsp.route(
            ctx,
            a["node"],
            b["node"],
            "walk",
            dep,
            0.0,
            date_id,
            "fastest_without_ac_link",
            blocked_edges=blocked,
        )
    except NoRoute:
        fs = free.stats
        return {
            "origin": ctx.poi(a_id)["name"],
            "dest": ctx.poi(b_id)["name"],
            "date_id": date_id,
            "depart": hhmm,
            "uses_ac_link": any(s["cls"] == "ac_link" for s in free.segments),
            "fastest_with_links": {
                k: fs[k] for k in ("distance_m", "duration_s", "sun_exposure_s", "indoor_pct", "rhl")
            },
            "without_ac_link": None,
            "note": "With the ac_link edges removed the destination is unreachable in the current graph: the "
            "metro station connects to the mall only through the link. Links are unverified on site.",
        }
    fs, os_ = free.stats, alt.stats
    return {
        "origin": ctx.poi(a_id)["name"],
        "dest": ctx.poi(b_id)["name"],
        "date_id": date_id,
        "depart": hhmm,
        "uses_ac_link": any(s["cls"] == "ac_link" for s in free.segments),
        "fastest_with_links": {
            k: fs[k] for k in ("distance_m", "duration_s", "sun_exposure_s", "indoor_pct", "rhl")
        },
        "without_ac_link": {
            k: os_[k] for k in ("distance_m", "duration_s", "sun_exposure_s", "indoor_pct", "rhl")
        },
        "sun_saved_s": round(os_["sun_exposure_s"] - fs["sun_exposure_s"], 2),
        "time_delta_s": round(fs["duration_s"] - os_["duration_s"], 2),
        "rhl_saved_pct": round(100.0 * (os_["rhl"] - fs["rhl"]) / os_["rhl"], 1) if os_["rhl"] else 0.0,
        "note": "Computed: same pair routed with and without the ac_link edges. Links unverified on site.",
    }


def generate(
    city_id: str = config.DEFAULT_CITY, out_path: Path | None = None, serial: bool = False, log: Any = print
) -> dict[str, Any]:
    ctx = get_city(city_id)
    places, place_filter = _places(ctx)
    attempts: list[dict[str, Any]] = []

    def attempt(name: str, lo: float, hi: float, departs: tuple[str, ...]):
        rows, info = run_search(ctx, places, lo, hi, departs, DATES, ("walk", "cycle"), serial)
        sel = select(rows)
        best_t = sel["tourist_walk"]["sun_saved_s"] if sel["tourist_walk"] else 0.0
        info.update(
            name=name,
            eligible=sum(1 for r in rows if r["eligible"]),
            best_tourist_sun_saved_s=best_t,
            selected={
                k: (
                    None
                    if v is None
                    else f"{v['origin']}->{v['dest']} {v['mode']} {v['depart']} {v['date_id']}"
                )
                for k, v in sel.items()
            },
        )
        attempts.append(info)
        log(
            f"[scenarios] {name}: {info['jobs']} jobs in {info['elapsed_s']}s, eligible {info['eligible']}, "
            f"best tourist sun_saved_s {best_t:.1f}"
        )
        return rows, sel

    rows, sel = attempt("baseline: curated places, pairs 400-1500 m, 4 departures", 400.0, 1500.0, DEPARTS)
    all_rows = list(rows)
    best = sel["tourist_walk"]["sun_saved_s"] if sel["tourist_walk"] else 0.0
    if best < MIN_TOURIST_SAVE_S:
        deps2 = ("11:30", "12:00", "12:30", "13:00", "13:30", "14:00", "14:30", "15:00", "15:30", "16:00")
        rows2, sel = attempt("widened: pairs 300-1800 m, 10 departures", 300.0, 1800.0, deps2)
        all_rows = rows2
    scen, notes = [], []
    for sid, persona in (("tourist_walk", "tourist"), ("rider_cycle", "rider"), ("crew_shuttle", "crew")):
        row = sel.get(sid)
        if row is None:
            notes.append(f"{sid}: no eligible candidate found")
            continue
        scen.append(_full(ctx, row, persona, sid, with_departure=(sid == "tourist_walk")))
    tour = sel["tourist_walk"]
    if tour is None or tour["sun_saved_s"] < MIN_TOURIST_SAVE_S:
        notes.append(
            f"Best tourist sun_saved_s is below {MIN_TOURIST_SAVE_S:.0f} s even after widening; "
            "the Film must present this honestly (lean on the departure optimiser and AC links)."
        )
    ranked = sorted((r for r in all_rows if r["eligible"]), key=lambda r: -r["sun_saved_s"])[:20]
    out = {
        "generated_at": datetime.now(ZoneInfo(ctx.tz)).isoformat(timespec="seconds"),
        "city": city_id,
        "search": {
            "procedure": __doc__.split("Procedure")[1].split("Sun-mode procedure")[0].strip()
            if __doc__
            else "",
            "place_filter": {"kinds": sorted(PLACE_KINDS), "snap_max_m": SNAP_MAX_M, **place_filter},
            "filters": {
                "max_network_ratio": MAX_NETWORK_RATIO,
                "max_duration_s": MAX_DURATION_S,
                "crew": {"max_straight_m": CREW_MAX_STRAIGHT_M, "max_duration_s": CREW_MAX_DURATION_S},
                "max_added_frac": MAX_ADDED_FRAC,
                "max_detour": MAX_DETOUR,
                "ac_preference_frac": AC_PREFERENCE_FRAC,
            },
            "attempts": attempts,
            "notes": notes,
            "min_tourist_sun_saved_s": MIN_TOURIST_SAVE_S,
            "lambdas": config.LAMBDAS,
            "model": "Model v1: buildings, mapped trees, covered links",
        },
        "scenarios": scen,
        "ac_link_story": ac_link_story(ctx, "metro_burj_khalifa", "dubai_mall"),
        "candidates": ranked,
    }
    path = out_path or (
        config.DATA_DIR
        / "scenarios"
        / ("hero.json" if city_id == config.DEFAULT_CITY else f"hero_{city_id}.json")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    prev = _read_json(path)
    if prev and "sun" in prev:  # the sun-mode block is generated separately (generate_sun)
        out["sun"] = prev["sun"]
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    log(f"[scenarios] wrote {path}")
    return out


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


# ---------------------------------------------------------------------------------------------
# Sun mode (overnight Stream A): documented search, written under hero.json["sun"]
# ---------------------------------------------------------------------------------------------
SUN_DATES = ("winter",)
SUN_MORNING_DEPARTS = ("09:00", "09:30", "10:00", "10:30", "11:00")
SUN_LUNCH_DEPARTS = ("12:00", "12:30", "13:00", "13:30")
MIN_SUN_GAIN_S = 90.0
LUNCH_MAX_DURATION_S = 15 * 60.0
SPRING_DATE = "spring"
SPRING_DEPARTS = ("10:00", "10:30", "11:00", "11:30")


def window_at(ctx: CityContext, date_id: str, hhmm: str) -> dict[str, Any]:
    """Daylight-window state at the city origin from the recorded weather (no network)."""
    from zill import weather, wellbeing
    from zill.sun.position import sun_position

    dep = ctx.at(date_id, hhmm)
    alt = sun_position(dep, ctx.origin["lat"], ctx.origin["lon"], ctx.tz).alt_deg
    w = weather.get(ctx.city_id, dep, allow_live=False, prefer_recorded=True)
    return wellbeing.daylight_window(
        alt, w.get("uv_index"), w.get("cloud_cover_pct"), w.get("clear_sky_index")
    )


def _rank_sun(rows: list[dict[str, Any]], departs: tuple[str, ...]) -> list[dict[str, Any]]:
    out = [r for r in rows if r["eligible"] and r["depart"] in departs]
    out.sort(key=lambda r: (-r["sun_gained_s"], r["added_time_s"], r["origin"], r["dest"], r["depart"]))
    t1 = [r for r in out if r.get("both_curated")]
    return t1 if t1 and t1[0]["sun_gained_s"] >= 60.0 else out


def select_sun(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any] | None]:
    morning = _rank_sun(rows, SUN_MORNING_DEPARTS)
    m = morning[0] if morning else None
    used = {frozenset((m["origin"], m["dest"]))} if m else set()
    lunch = [
        r
        for r in _rank_sun(rows, SUN_LUNCH_DEPARTS)
        if r["fastest_duration_s"] <= LUNCH_MAX_DURATION_S and frozenset((r["origin"], r["dest"])) not in used
    ]
    return {"winter_morning_walk": m, "office_lunch_walk": lunch[0] if lunch else None}


def _full_sun(
    ctx: CityContext, row: dict[str, Any], persona: str, sid: str, with_departure: bool
) -> dict[str, Any]:
    from zill import weather, wellbeing
    from zill.sun.position import sun_position

    mode, date_id, hh = row["mode"], row["date_id"], row["depart"]
    a = ctx.resolve_place({"poi": row["origin"]}, mode)
    b = ctx.resolve_place({"poi": row["dest"]}, mode)
    dep = ctx.at(date_id, hh)
    res = tdsp.compare(ctx, a["node"], b["node"], mode, dep, date_id, with_geometry=True, preference="sun")

    def pl(p: dict[str, Any], name: str) -> dict[str, Any]:
        return {"name": name, "lat": p["lat"], "lon": p["lon"], "node": p["node"], "x": p["x"], "z": p["z"]}

    sunny = res["sunniest"]
    alt = sun_position(dep, ctx.origin["lat"], ctx.origin["lon"], ctx.tz).alt_deg
    w = weather.get(ctx.city_id, dep, allow_live=False, prefer_recorded=True)
    w.pop("hourly", None)
    out: dict[str, Any] = {
        "id": sid,
        "persona": persona,
        "preference": "sun",
        "mode": mode,
        "origin": pl(a, row["origin_name"]),
        "dest": pl(b, row["dest_name"]),
        "date_id": date_id,
        "depart": hh,
        "straight_m": row["straight_m"],
        "fastest": res["fastest"].to_dict(),
        "sunniest": sunny.to_dict(),
        "balanced": res["balanced"].to_dict(),
        "wellbeing": wellbeing.assess("sun", alt, w, sunny.stats, sunny.segments),
        "departure": None,
    }
    if with_departure:
        d = optimise_departure(
            ctx,
            a["node"],
            b["node"],
            mode,
            dep,
            dep + timedelta(minutes=90),
            date_key=date_id,
            preference="sun",
        )
        out["departure"] = d.to_dict()
    return out


# S8: per-city sun-mode plans (Dubai keeps the S1-S7 procedure above)
SUN_CITY_PLANS: dict[str, list[dict[str, Any]]] = {
    "oslo": [
        {
            "id": "solstice_midday_walk",
            "persona": "daylight_seeker",
            "date_id": "winter",  # 2026-12-21: sun ~6.6 deg at noon; daylight and mood, not vitamin D
            "departs": ("11:30", "12:00", "12:30", "13:00"),
            "open_window": False,
        },
        {
            "id": "summer_daylight_walk",
            "persona": "daylight_seeker",
            "date_id": "summer",  # 2026-06-21
            "departs": ("11:00", "11:30", "12:00", "12:30", "13:00", "13:30", "14:00"),
            "open_window": True,
        },
    ],
}


def _write_sun_block(ctx: CityContext, out_path: Path | None, block: dict[str, Any], log: Any) -> None:
    path = out_path or (
        config.DATA_DIR
        / "scenarios"
        / ("hero.json" if ctx.city_id == config.DEFAULT_CITY else f"hero_{ctx.city_id}.json")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    full = _read_json(path) or {}
    full["sun"] = block
    path.write_text(json.dumps(full, indent=1), encoding="utf-8")
    log(f"[scenarios:sun] wrote {path} (key 'sun')")


def _scenario_notes(scen: list[dict[str, Any]]) -> list[str]:
    notes = []
    for sc in scen:
        wb = sc["wellbeing"]
        if wb.get("overcast"):
            notes.append(f"{sc['id']}: recorded weather shows {wb['overcast']['text']}")
        if not wb["daylight_window"]["active"]:
            notes.append(f"{sc['id']}: {wb['daylight_window']['text']}")
        if wb["uv"]["band"] in ("very high", "extreme"):
            uv = wb["uv"]
            notes.append(f"{sc['id']}: UV index {uv['index']} is {uv['band']}. {uv['advice']}")
        lbl = (wb.get("weather") or {}).get("label") or ""
        if "stand-in" in lbl or "Representative" in lbl:
            notes.append(f"{sc['id']}: weather is {lbl}")
    return notes


def generate_sun_plan(
    ctx: CityContext, plan: list[dict[str, Any]], out_path: Path | None, serial: bool, log: Any
) -> dict[str, Any]:
    """S8: plan-driven sun-mode search for a city (see SUN_CITY_PLANS)."""
    places, place_filter = _places(ctx)
    attempts: list[dict[str, Any]] = []
    scen: list[dict[str, Any]] = []
    notes: list[str] = []
    cands: dict[str, list[dict[str, Any]]] = {}
    used: set[frozenset[str]] = set()
    for item in plan:
        sid, date_id = item["id"], item["date_id"]
        if not ctx.has_exposure(date_id):
            notes.append(f"{sid}: no exposure table for {date_id}")
            continue
        win = {hh: window_at(ctx, date_id, hh) for hh in item["departs"]}
        deps = (
            tuple(hh for hh in item["departs"] if win[hh]["active"])
            if item["open_window"]
            else item["departs"]
        )
        winfo = {hh: {"active": w["active"], "reasons": w["reasons"]} for hh, w in win.items()}
        if not deps:
            attempts.append({"name": f"{sid}: no departure with an open window", "windows": winfo, "jobs": 0})
            notes.append(f"{sid}: no departure on {date_id} has an open daylight window")
            continue
        pick = None
        for name, lo, hi in (
            (f"{sid}: pairs 400-1500 m", 400.0, 1500.0),
            (f"{sid}: widened 300-1800 m", 300.0, 1800.0),
        ):
            rows, info = run_search(
                ctx, places, lo, hi, deps, (date_id,), ("walk",), serial, preference="sun"
            )
            pool = [r for r in _rank_sun(rows, deps) if frozenset((r["origin"], r["dest"])) not in used]
            pick = pool[0] if pool else None
            info.update(
                name=name,
                windows=winfo,
                eligible=sum(1 for r in rows if r["eligible"]),
                best_sun_gained_s=pick["sun_gained_s"] if pick else 0.0,
                selected=None
                if pick is None
                else f"{pick['origin']}->{pick['dest']} walk {pick['depart']} {date_id}",
            )
            attempts.append(info)
            log(f"[scenarios:sun] {name}: {info['jobs']} jobs, eligible {info['eligible']}")
            cands[sid] = sorted((r for r in rows if r["eligible"]), key=lambda r: -r["sun_gained_s"])[:20]
            if pick is not None and pick["sun_gained_s"] >= MIN_SUN_GAIN_S:
                break
        if pick is None:
            notes.append(f"{sid}: no eligible candidate found")
            continue
        used.add(frozenset((pick["origin"], pick["dest"])))
        scen.append(_full_sun(ctx, pick, item["persona"], sid, with_departure=False))
    notes.extend(_scenario_notes(scen))
    doc = __doc__ or ""
    block = {
        "generated_at": datetime.now(ZoneInfo(ctx.tz)).isoformat(timespec="seconds"),
        "city": ctx.city_id,
        "search": {
            "procedure": ("S8." + doc.split("S8.", 1)[1]).strip() if "S8." in doc else "",
            "plan": [{**i, "departs": list(i["departs"])} for i in plan],
            "place_filter": {"kinds": sorted(PLACE_KINDS), "snap_max_m": SNAP_MAX_M, **place_filter},
            "filters": {
                "max_network_ratio": MAX_NETWORK_RATIO,
                "max_duration_s": MAX_DURATION_S,
                "max_added_frac": MAX_ADDED_FRAC,
                "max_detour": MAX_DETOUR,
            },
            "attempts": attempts,
            "notes": notes,
            "min_sun_gained_s": MIN_SUN_GAIN_S,
            "lambdas": config.LAMBDAS,
            "cost": "t + lam * SUN_WEIGHT[mode] * shade_time (shade_time = time not in direct sun)",
            "model": "Model v1: buildings, mapped trees, covered links; clear-sky geometry",
        },
        "scenarios": scen,
        "candidates": cands,
    }
    _write_sun_block(ctx, out_path, block, log)
    return block


def generate_sun(
    city_id: str = config.DEFAULT_CITY, out_path: Path | None = None, serial: bool = False, log: Any = print
) -> dict[str, Any]:
    """Run the sun-mode search and write it under the `sun` key of hero.json (other keys untouched)."""
    ctx = get_city(city_id)
    if city_id in SUN_CITY_PLANS:
        return generate_sun_plan(ctx, SUN_CITY_PLANS[city_id], out_path, serial, log)
    places, place_filter = _places(ctx)
    departs = SUN_MORNING_DEPARTS + SUN_LUNCH_DEPARTS
    attempts: list[dict[str, Any]] = []

    def attempt(name: str, lo: float, hi: float) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        rows, info = run_search(ctx, places, lo, hi, departs, SUN_DATES, ("walk",), serial, preference="sun")
        sel = select_sun(rows)
        best = sel["winter_morning_walk"]["sun_gained_s"] if sel["winter_morning_walk"] else 0.0
        info.update(
            name=name,
            eligible=sum(1 for r in rows if r["eligible"]),
            best_morning_sun_gained_s=best,
            selected={
                k: (
                    None
                    if v is None
                    else f"{v['origin']}->{v['dest']} {v['mode']} {v['depart']} {v['date_id']}"
                )
                for k, v in sel.items()
            },
        )
        attempts.append(info)
        log(
            f"[scenarios:sun] {name}: {info['jobs']} jobs in {info['elapsed_s']}s, "
            f"eligible {info['eligible']}, "
            f"best morning sun_gained_s {best:.1f}"
        )
        return rows, sel

    rows, sel = attempt("baseline: curated places, pairs 400-1500 m, winter morning + lunch", 400.0, 1500.0)
    m = sel["winter_morning_walk"]
    if m is None or m["sun_gained_s"] < MIN_SUN_GAIN_S:
        rows, sel = attempt("widened: pairs 300-1800 m", 300.0, 1800.0)
    scen, notes = [], []
    for sid, persona in (("winter_morning_walk", "daylight_seeker"), ("office_lunch_walk", "office_worker")):
        row = sel.get(sid)
        if row is None:
            notes.append(f"{sid}: no eligible candidate found")
            continue
        scen.append(_full_sun(ctx, row, persona, sid, with_departure=(sid == "winter_morning_walk")))
    # S7: spring late morning, only departures whose daylight window is open
    spring_rows: list[dict[str, Any]] = []
    if ctx.has_exposure(SPRING_DATE):
        win = {hh: window_at(ctx, SPRING_DATE, hh) for hh in SPRING_DEPARTS}
        open_deps = tuple(hh for hh in SPRING_DEPARTS if win[hh]["active"])
        info_w = {hh: {"active": w["active"], "reasons": w["reasons"]} for hh, w in win.items()}
        if open_deps:
            spring_rows, info = run_search(
                ctx, places, 400.0, 1500.0, open_deps, (SPRING_DATE,), ("walk",), serial, preference="sun"
            )
            used = {frozenset((r["origin"], r["dest"])) for r in (sel.get(k) for k in sel) if r}
            pool = [
                r
                for r in _rank_sun(spring_rows, open_deps)
                if frozenset((r["origin"], r["dest"])) not in used
            ]
            info.update(
                name="spring late morning, open daylight window only",
                windows=info_w,
                eligible=sum(1 for r in spring_rows if r["eligible"]),
                selected={
                    "spring_daylight_walk": None
                    if not pool
                    else f"{pool[0]['origin']}->{pool[0]['dest']} walk {pool[0]['depart']} {SPRING_DATE}"
                },
            )
            attempts.append(info)
            log(f"[scenarios:sun] spring: {info['jobs']} jobs, eligible {info['eligible']}")
            if pool:
                scen.append(
                    _full_sun(ctx, pool[0], "daylight_seeker", "spring_daylight_walk", with_departure=False)
                )
            else:
                notes.append("spring_daylight_walk: no eligible candidate found")
        else:
            attempts.append({"name": "spring late morning", "windows": info_w, "jobs": 0})
            notes.append("spring_daylight_walk: no spring late-morning departure has an open daylight window")
    else:
        notes.append("spring_daylight_walk: no spring exposure table")
    for sc in scen:
        wb = sc["wellbeing"]
        if wb.get("overcast"):
            notes.append(f"{sc['id']}: recorded weather shows {wb['overcast']['text']}")
        if not wb["daylight_window"]["active"]:
            notes.append(f"{sc['id']}: {wb['daylight_window']['text']}")
        if wb["uv"]["band"] in ("very high", "extreme"):
            uv = wb["uv"]
            notes.append(f"{sc['id']}: UV index {uv['index']} is {uv['band']}. {uv['advice']}")
    ranked = sorted((r for r in rows if r["eligible"]), key=lambda r: -r["sun_gained_s"])[:20]
    doc = __doc__ or ""
    block = {
        "generated_at": datetime.now(ZoneInfo(ctx.tz)).isoformat(timespec="seconds"),
        "city": city_id,
        "search": {
            "procedure": ("S1." + doc.split("S1.", 1)[1]).strip() if "S1." in doc else "",
            "place_filter": {"kinds": sorted(PLACE_KINDS), "snap_max_m": SNAP_MAX_M, **place_filter},
            "filters": {
                "max_network_ratio": MAX_NETWORK_RATIO,
                "max_duration_s": MAX_DURATION_S,
                "lunch_max_duration_s": LUNCH_MAX_DURATION_S,
                "max_added_frac": MAX_ADDED_FRAC,
                "max_detour": MAX_DETOUR,
            },
            "attempts": attempts,
            "notes": notes,
            "min_sun_gained_s": MIN_SUN_GAIN_S,
            "lambdas": config.LAMBDAS,
            "cost": "t + lam * SUN_WEIGHT[mode] * shade_time (shade_time = time not in direct sun)",
            "model": "Model v1: buildings, mapped trees, covered links; clear-sky geometry",
        },
        "scenarios": scen,
        "candidates": ranked,
        "candidates_spring": sorted(
            (r for r in spring_rows if r["eligible"]), key=lambda r: -r["sun_gained_s"]
        )[:20],
    }
    path = out_path or (
        config.DATA_DIR
        / "scenarios"
        / ("hero.json" if city_id == config.DEFAULT_CITY else f"hero_{city_id}.json")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    full = _read_json(path) or {}
    full["sun"] = block
    path.write_text(json.dumps(full, indent=1), encoding="utf-8")
    log(f"[scenarios:sun] wrote {path} (key 'sun')")
    return block


def headline_sun(block: dict[str, Any]) -> list[str]:
    lines = []
    for s in block["scenarios"]:
        f, c = s["fastest"]["stats"], s["sunniest"]["stats"]
        wb = s["wellbeing"]
        lines.append(
            f"{s['id']}: {s['origin']['name']} -> {s['dest']['name']} {s['mode']} "
            f"{s['date_id']} {s['depart']} "
            f"fastest {f['duration_s']:.0f}s/{f['sun_exposure_s']:.0f}s sun | sunniest "
            f"{c['duration_s']:.0f}s/{c['sun_exposure_s']:.0f}s sun | gained {c['sun_gained_s']:.0f}s "
            f"({c['sun_gained_pct']:.0f}%), +{c['added_time_s']:.0f}s | "
            f"alt {wb['daylight_window']['sun_alt_deg']} "
            f"uv {wb['uv']['index']} cloud {wb['weather']['cloud_cover_pct']}% window "
            f"{wb['daylight_window']['active']}"
        )
    return lines


def headline(out: dict[str, Any]) -> list[str]:
    lines = []
    for s in out["scenarios"]:
        f, c = s["fastest"]["stats"], s["coolest"]["stats"]
        lines.append(
            f"{s['id']}: {s['origin']['name']} -> {s['dest']['name']} {s['mode']} "
            f"{s['date_id']} {s['depart']} "
            f"(straight {s['straight_m']:.0f} m, ac_link={s['uses_ac_link']}, covered={s['uses_covered']}, "
            f"indoor={s['uses_indoor']})  fastest {f['duration_s']:.0f}s/{f['sun_exposure_s']:.0f}s sun | "
            f"coolest {c['duration_s']:.0f}s/{c['sun_exposure_s']:.0f}s sun | saved {c['sun_saved_s']:.0f}s "
            f"({c['sun_saved_pct']:.0f}%), +{c['added_time_s']:.0f}s, rhl -{c['rhl_saved_pct']:.0f}%"
        )
    return lines


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default=config.DEFAULT_CITY)
    ap.add_argument("--out", default=None)
    ap.add_argument("--serial", action="store_true")
    ap.add_argument("--sun", action="store_true", help="run only the sun-mode search (writes key 'sun')")
    a = ap.parse_args()
    if a.sun:
        print("\n".join(headline_sun(generate_sun(a.city, Path(a.out) if a.out else None, a.serial))))
    else:
        res = generate(a.city, Path(a.out) if a.out else None, a.serial)
        print("\n".join(headline(res)))

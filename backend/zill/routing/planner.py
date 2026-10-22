"""Multi-stop day / shift planner (PRD 8.5, P1).

* ordering: exhaustive permutations up to PLAN_MAX_PERMUTE_STOPS stops, beam search above, scored on a
  coarse pairwise matrix (Balanced routes at the start time) with time windows simulated;
* execution: every leg is routed time-dependently at its real clock time;
* cool-down breaks (nearest indoor / AC / cafe POI) are inserted when the Relative Heat Load of the
  rolling RHL_BREAK_WINDOW_MIN minutes would exceed RHL_BREAK_THRESHOLD;
* crew persona: outdoor dwell counts as outdoor work (sun taken from the edges at the site), an optional
  shift window picks the start with the fewest policy conflicts then the lowest heat load;
* policy conflicts come from the policy pack (`zill.agent.policy.check_policy`, pack is data and
  `verified: false`; never legal advice).
"""

from __future__ import annotations

import itertools
import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from zill import config
from zill.routing import tdsp
from zill.routing.graph import NoRoute
from zill.services import CityContext

COOL_KINDS = {"mall", "hotel", "metro", "cafe", "museum", "station"}
LATE_PENALTY = 1e6
LAMBDA = config.LAMBDAS["balanced"]


@dataclass
class Stop:
    index: int
    name: str
    node: int
    x: float
    z: float
    dwell_s: float
    window: tuple[datetime, datetime] | None = None
    fixed: bool = False
    kind: str | None = None

    @property
    def cool(self) -> bool:
        return self.kind in COOL_KINDS


def _site_sun(ctx: CityContext, tab: Any, node: int, minute: float) -> float:
    g = ctx.graph
    mask = (g.eu == node) | (g.ev == node)
    idx = [int(e) for e in mask.nonzero()[0] if int(g.cls[e]) == 0]
    if not idx:
        return 0.0
    return float(sum(tab.sun(e, minute) for e in idx) / len(idx))


def _nearest_poi_kind(ctx: CityContext, x: float, z: float, within_m: float = 60.0) -> str | None:
    best, bd = None, within_m
    for p in ctx.pois:
        d = math.hypot(p["x"] - x, p["z"] - z)
        if d <= bd:
            best, bd = p, d
    return best.get("kind") if best else None


class _Router:
    """Leg router with a small cache (balanced route, no geometry)."""

    def __init__(self, ctx: CityContext, mode: str, date_key: str) -> None:
        self.ctx, self.mode, self.date_key = ctx, mode, date_key
        self.cache: dict[tuple[int, int, int], tdsp.RouteResult | None] = {}

    def leg(self, a: int, b: int, depart: datetime, geometry: bool = False) -> tdsp.RouteResult | None:
        if a == b:
            return None
        if geometry:
            return tdsp.route(
                self.ctx,
                a,
                b,
                self.mode,
                depart,
                LAMBDA,
                self.date_key,
                "balanced",
                with_geometry=True,
                relative=False,
            )
        key = (a, b, int(depart.timestamp() // 600))
        if key not in self.cache:
            try:
                self.cache[key] = tdsp.route(
                    self.ctx,
                    a,
                    b,
                    self.mode,
                    depart,
                    LAMBDA,
                    self.date_key,
                    "balanced",
                    with_geometry=False,
                    relative=False,
                )
            except NoRoute:
                self.cache[key] = None
        return self.cache[key]


def _score_order(rt: _Router, start: Stop, order: list[Stop], t0: datetime, mu: float) -> float:
    """Heuristic cost of an order: sum of leg RHL + mu*time, with windows simulated on the clock."""
    clock, cur, total = t0, start, 0.0
    for st in order:
        r = rt.leg(cur.node, st.node, clock)
        if r is None and cur.node != st.node:
            return math.inf
        dur = r.stats["duration_s"] if r else 0.0
        total += (r.stats["rhl"] if r else 0.0) + mu * dur
        clock += timedelta(seconds=dur)
        if st.window:
            if clock < st.window[0]:
                total += mu * (st.window[0] - clock).total_seconds()
                clock = st.window[0]
            elif clock > st.window[1]:
                total += LATE_PENALTY + (clock - st.window[1]).total_seconds()
        clock += timedelta(seconds=st.dwell_s)
        cur = st
    return total


def choose_order(
    rt: _Router, start: Stop, stops: list[Stop], t0: datetime, reorder: bool, mu: float = 0.25
) -> list[Stop]:
    if not reorder or len(stops) <= 1:
        return list(stops)
    free_slots = [i for i, s in enumerate(stops) if not s.fixed]
    free = [stops[i] for i in free_slots]

    def assemble(perm: list[Stop]) -> list[Stop]:
        out = list(stops)
        for slot, st in zip(free_slots, perm, strict=True):
            out[slot] = st
        return out

    if len(free) <= 1:
        return list(stops)
    if len(free) <= config.PLAN_MAX_PERMUTE_STOPS:
        best, best_c = None, math.inf
        for perm in itertools.permutations(free):
            cand = assemble(list(perm))
            c = _score_order(rt, start, cand, t0, mu)
            if c < best_c:
                best, best_c = cand, c
        return best or list(stops)
    # beam search over the free stops (fixed stops keep their slots; approximated by scoring full orders)
    beam: list[list[Stop]] = [[]]
    for _ in range(len(free)):
        nxt: list[tuple[float, list[Stop]]] = []
        for pref in beam:
            for st in free:
                if st in pref:
                    continue
                cand_pref = [*pref, st]
                rest = [s for s in free if s not in cand_pref]
                c = _score_order(rt, start, assemble([*cand_pref, *rest]), t0, mu)
                nxt.append((c, cand_pref))
        nxt.sort(key=lambda x: x[0])
        beam = [p for _, p in nxt[:12]]
    return assemble(beam[0])


def _leg_item(r: tdsp.RouteResult, a: Stop, b: Stop, depart: datetime, label: str) -> dict[str, Any]:
    st = r.stats
    end = depart + timedelta(seconds=st["duration_s"])
    return {
        "kind": "leg",
        "label": label,
        "from": a.name,
        "to": b.name,
        "start": depart.isoformat(),
        "end": end.isoformat(),
        "duration_s": st["duration_s"],
        "distance_m": st["distance_m"],
        "sun_exposure_s": st["sun_exposure_s"],
        "shaded_pct": st["shaded_pct"],
        "rhl": st["rhl"],
        "outdoor_work": True,
        "edges": r.edges,
        "nodes": r.nodes,
    }


def _find_cool_break(
    ctx: CityContext, rt: _Router, here: Stop, nxt: Stop, clock: datetime
) -> tuple[dict[str, Any], tdsp.RouteResult, tdsp.RouteResult | None] | None:
    cands = []
    for p in ctx.pois:
        if p.get("kind") in COOL_KINDS and p.get("node") is not None:
            d = math.hypot(p["x"] - here.x, p["z"] - here.z)
            if d <= 450:
                cands.append((d, p))
    cands.sort(key=lambda c: c[0])
    best = None
    for _, p in cands[:5]:
        a = rt.leg(here.node, int(p["node"]), clock)
        if a is None:
            continue
        b_clock = clock + timedelta(seconds=a.stats["duration_s"] + config.COOLDOWN_BREAK_MIN * 60)
        b = rt.leg(int(p["node"]), nxt.node, b_clock)
        if b is None and int(p["node"]) != nxt.node:
            continue
        cost = a.stats["rhl"] + (b.stats["rhl"] if b else 0.0)
        if best is None or cost < best[0]:
            best = (cost, p, a, b)
    return None if best is None else (best[1], best[2], best[3])


def _execute(
    ctx: CityContext,
    rt: _Router,
    tab: Any,
    persona: str,
    start: Stop,
    order: list[Stop],
    t0: datetime,
    return_to_start: bool,
) -> dict[str, Any]:
    clock, cur = t0, start
    items: list[dict[str, Any]] = []
    legs: list[dict[str, Any]] = []
    breaks: list[dict[str, Any]] = []
    stop_rows: list[dict[str, Any]] = []
    window: list[tuple[datetime, float]] = []  # (end time, rhl) of recent outdoor items
    notes: list[str] = []
    seq = [*order, *([start] if return_to_start else [])]
    thr, win = config.RHL_BREAK_THRESHOLD, timedelta(minutes=config.RHL_BREAK_WINDOW_MIN)

    def rolling(now: datetime) -> float:
        return sum(r for e, r in window if e > now - win)

    for st in seq:
        r = rt.leg(cur.node, st.node, clock, geometry=False)
        if r is None and cur.node != st.node:
            raise NoRoute(f"no {rt.mode} route from {cur.name} to {st.name}")
        if r is not None and rolling(clock) + r.stats["rhl"] > thr:
            br = _find_cool_break(ctx, rt, cur, st, clock)
            if br is not None:
                poi, a, b = br
                brk_stop = Stop(
                    -1, poi["name"], int(poi["node"]), poi["x"], poi["z"], 0.0, kind=poi.get("kind")
                )
                if a is not None and a.nodes and len(a.edges):
                    ra = rt.leg(cur.node, brk_stop.node, clock, geometry=True)
                    legs.append(
                        {**_leg_item(ra, cur, brk_stop, clock, "to cool-down break"), "route": ra.to_dict()}
                    )
                    items.append(_leg_item(ra, cur, brk_stop, clock, "to cool-down break"))
                    window.append((clock + timedelta(seconds=ra.stats["duration_s"]), ra.stats["rhl"]))
                    clock += timedelta(seconds=ra.stats["duration_s"])
                end = clock + timedelta(minutes=config.COOLDOWN_BREAK_MIN)
                brow = {
                    "kind": "break",
                    "label": f"Cool-down at {poi['name']}",
                    "place": poi["name"],
                    "poi": poi["id"],
                    "start": clock.isoformat(),
                    "end": end.isoformat(),
                    "reason": "rolling heat load would exceed the break threshold",
                    "outdoor_work": False,
                    "sun_exposure_s": 0.0,
                }
                breaks.append(brow)
                items.append(brow)
                window.clear()
                clock, cur = end, brk_stop
                r = rt.leg(cur.node, st.node, clock, geometry=False)
            else:
                notes.append(f"No cool-down venue within 450 m of {cur.name}; heat-load threshold exceeded.")
        if r is not None:
            rg = rt.leg(cur.node, st.node, clock, geometry=True)
            li = _leg_item(rg, cur, st, clock, f"{cur.name} to {st.name}")
            legs.append({**li, "route": rg.to_dict()})
            items.append(li)
            window.append((clock + timedelta(seconds=rg.stats["duration_s"]), rg.stats["rhl"]))
            clock += timedelta(seconds=rg.stats["duration_s"])
        arrive = clock
        wait_s = 0.0
        late = False
        if st.window:
            if clock < st.window[0]:
                wait_s = (st.window[0] - clock).total_seconds()
                clock = st.window[0]
            elif clock > st.window[1]:
                late = True
        row = {
            "index": st.index,
            "name": st.name,
            "node": st.node,
            "arrive": arrive.isoformat(),
            "wait_s": wait_s,
            "late": late,
            "dwell_s": st.dwell_s,
        }
        if st.dwell_s > 0 and st is not start:
            end = clock + timedelta(seconds=st.dwell_s)
            if persona == "crew":
                mid = tab.minute_of(clock + timedelta(seconds=st.dwell_s / 2))
                sun = _site_sun(ctx, tab, st.node, mid)
                it = {
                    "kind": "work",
                    "label": f"Work at {st.name}",
                    "place": st.name,
                    "start": clock.isoformat(),
                    "end": end.isoformat(),
                    "sun_exposure_s": round(sun * st.dwell_s, 1),
                    "site_sun": round(sun, 3),
                    "outdoor_work": True,
                    "note": "site sun = mean exposure of the open edges at the site node",
                }
                items.append(it)
                window.append((end, st.dwell_s * (sun * config.RHL_SUN + (1 - sun) * config.RHL_SHADE)))
            else:
                it = {
                    "kind": "dwell",
                    "label": f"At {st.name}",
                    "place": st.name,
                    "start": clock.isoformat(),
                    "end": end.isoformat(),
                    "sun_exposure_s": 0.0,
                    "outdoor_work": False,
                }
                items.append(it)
                if st.cool:
                    window.clear()
            clock = end
        stop_rows.append(row)
        cur = st
    outdoor = [i for i in items if i["kind"] in ("leg", "work")]
    totals = {
        "start": t0.isoformat(),
        "end": clock.isoformat(),
        "duration_s": (clock - t0).total_seconds(),
        "walk_distance_m": round(sum(i.get("distance_m", 0.0) for i in items if i["kind"] == "leg"), 1),
        "sun_exposure_s": round(sum(i["sun_exposure_s"] for i in outdoor), 1),
        "rhl": round(sum(i["rhl"] for i in items if i["kind"] == "leg"), 1),
        "breaks": len(breaks),
        "late_stops": sum(1 for s in stop_rows if s["late"]),
    }
    return {
        "items": items,
        "legs": legs,
        "breaks": breaks,
        "stops": stop_rows,
        "totals": totals,
        "notes": notes,
    }


def check_policy(plan: dict[str, Any], pack_id: str = "UAE_OUTDOOR_WORK") -> dict[str, Any]:
    """Policy conflicts for a plan (items with start/end/sun_exposure_s). Pack is unverified data."""
    from zill.agent import policy

    return policy.check_policy({"items": plan["items"], "persona": plan.get("persona", "crew")}, pack_id)


def plan(
    ctx: CityContext,
    mode: str,
    persona: str,
    start_place: dict[str, Any],
    stops: list[Stop],
    start_at: datetime,
    date_key: str,
    reorder: bool = True,
    return_to_start: bool = False,
    policy_pack: str | None = None,
    shift_window: tuple[datetime, datetime] | None = None,
    mu: float = config.DEPARTURE_MU,
) -> dict[str, Any]:
    tab = ctx.exposure(date_key)
    rt = _Router(ctx, mode, date_key)
    start = Stop(
        -1,
        start_place["name"],
        start_place["node"],
        start_place["x"],
        start_place["z"],
        0.0,
        kind=_nearest_poi_kind(ctx, start_place["x"], start_place["z"]),
    )
    pack = policy_pack or ("UAE_OUTDOOR_WORK" if persona == "crew" else None)

    starts = [start_at]
    if persona == "crew" and shift_window:
        s0, s1 = shift_window
        starts = []
        t = s0
        while t <= s1 and len(starts) < 6:
            starts.append(t)
            t += timedelta(minutes=max(20, int((s1 - s0).total_seconds() / 60 / 5)))
    best: tuple[tuple[int, float], dict[str, Any], list[Stop]] | None = None
    for t0 in starts:
        order = choose_order(rt, start, stops, t0, reorder, mu)
        res = _execute(ctx, rt, tab, persona, start, order, t0, return_to_start)
        pol = check_policy({"items": res["items"], "persona": persona}, pack) if pack else None
        res["policy"] = pol
        key = (pol["count"] if pol else 0, res["totals"]["rhl"] + mu * res["totals"]["duration_s"])
        if shift_window and datetime.fromisoformat(res["totals"]["end"]) > shift_window[1]:
            key = (key[0] + 1000, key[1])
        if best is None or key < best[0]:
            best = (key, res, order)
    assert best is not None
    _, res, order = best
    res["order"] = [s.index for s in order]
    res["plan_id"] = "plan_" + uuid.uuid4().hex[:8]
    res["persona"] = persona
    res["mode"] = mode
    res["date_key"] = date_key
    if shift_window and len(starts) > 1:
        res["shift_search"] = {
            "candidates": [s.isoformat() for s in starts],
            "chosen": res["totals"]["start"],
        }
    return res


def plan_from_request(ctx: CityContext, req: Any, start_at: datetime, date_key: str) -> dict[str, Any]:
    from zill.api.common import ApiError
    from zill.api.routes_route import resolve_times

    def pin(p: Any) -> Any:
        return p.model_dump(exclude_none=True) if hasattr(p, "model_dump") else p

    first = req.start if req.start is not None else req.stops[0].place
    sp = ctx.resolve_place(pin(first), req.mode)
    stops: list[Stop] = []
    skip_first = req.start is None
    for i, s in enumerate(req.stops):
        if skip_first and i == 0:
            continue
        pl = ctx.resolve_place(pin(s.place), req.mode)
        win = None
        if s.window:
            if len(s.window) != 2:
                raise ApiError(422, "bad_window", "stop window must be [earliest, latest]")
            win = (resolve_times(ctx, s.window[0], date_key)[0], resolve_times(ctx, s.window[1], date_key)[0])
        stops.append(
            Stop(
                i,
                pl["name"],
                pl["node"],
                pl["x"],
                pl["z"],
                float(s.dwell_min) * 60.0,
                win,
                s.fixed,
                _nearest_poi_kind(ctx, pl["x"], pl["z"]),
            )
        )
    if not stops:
        raise ApiError(422, "bad_stops", "need at least one stop besides the start")
    sw = None
    sw_raw = getattr(req, "shift_window", None)
    if sw_raw:
        sw = (resolve_times(ctx, sw_raw[0], date_key)[0], resolve_times(ctx, sw_raw[1], date_key)[0])
    out = plan(
        ctx,
        req.mode,
        req.persona,
        sp,
        stops,
        start_at,
        date_key,
        req.reorder,
        req.return_to_start,
        req.policy_pack,
        sw,
    )
    out["start"] = sp
    return out

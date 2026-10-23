"""Departure-time optimiser (PRD 8.4).

Evaluates the Balanced route for every departure in a window and recommends the departure that
minimises ``rhl + mu * wait_s`` (waiting has a cost), subject to ``latest_arrival``. The `why`
struct lists the stretches of the recommended route whose sun state differs from what the
traveller would have met by leaving at the requested time.

Sun mode (preference="sun", overnight Stream A): the Balanced route is the sun-mode lam=1 route and the
score is ``shade_s + mu * wait_s`` (shade_s = seconds NOT in direct sun), i.e. it maximises sun.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from zill import config
from zill.routing import tdsp
from zill.routing.suntable import SunTable
from zill.services import CityContext

SUN_CHANGE_THRESHOLD = 0.4


@dataclass
class DepartureResult:
    table: list[dict[str, Any]]
    recommended: dict[str, Any]
    requested: dict[str, Any]
    why: dict[str, Any]
    date_key: str = ""
    route_recommended: tdsp.RouteResult | None = field(default=None, repr=False)
    route_requested: tdsp.RouteResult | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "table": self.table,
            "recommended": self.recommended,
            "requested": self.requested,
            "why": self.why,
            "date_key": self.date_key,
        }


def _hhmm(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def _row(
    r: tdsp.RouteResult, depart: datetime, window_start: datetime, latest: datetime | None
) -> dict[str, Any]:
    arrive = depart + timedelta(seconds=r.stats["duration_s"])
    st = r.stats
    return {
        "depart": depart.isoformat(),
        "depart_time": _hhmm(depart),
        "duration_s": st["duration_s"],
        "sun_exposure_s": st["sun_exposure_s"],
        "shaded_pct": st["shaded_pct"],
        "rhl": st["rhl"],
        "wait_s": (depart - window_start).total_seconds(),
        "arrive": arrive.isoformat(),
        "arrive_time": _hhmm(arrive),
        "feasible": latest is None or arrive <= latest,
    }


def _resolve_time(ctx: CityContext, s: str | datetime | None, date_key: str) -> datetime | None:
    if s is None or isinstance(s, datetime):
        return s
    if len(s) <= 5:  # HH:MM
        return ctx.at(date_key, s)
    return datetime.fromisoformat(s)


def optimise_departure(
    ctx: CityContext,
    o: Any,
    d: Any,
    mode: str,
    window_start: datetime,
    window_end: datetime | None = None,
    step_min: int = config.DEPARTURE_STEP_MIN,
    latest_arrival: datetime | None = None,
    mu: float = config.DEPARTURE_MU,
    date_key: str | None = None,
    requested: datetime | None = None,
    preference: str = "shade",
) -> DepartureResult:
    tdsp.check_preference(preference)
    sun = preference == "sun"
    rkw: dict[str, Any] = {"preference": "sun"} if sun else {}
    date_key = date_key or window_start.date().isoformat()
    tab = ctx.exposure(date_key)
    window_end = window_end or window_start + timedelta(minutes=90)
    requested = requested or window_start
    lam = config.LAMBDAS["balanced"]
    departs: list[datetime] = []
    t = window_start
    while t <= window_end + timedelta(seconds=1):
        departs.append(t)
        t += timedelta(minutes=step_min)

    def one(dep: datetime) -> tuple[datetime, tdsp.RouteResult]:
        return dep, tdsp.route(
            ctx, o, d, mode, dep, lam, date_key, "balanced", with_geometry=False, relative=False, **rkw
        )

    with ThreadPoolExecutor(max_workers=min(8, len(departs))) as ex:
        results = list(ex.map(one, departs))

    table = [_row(r, dep, window_start, latest_arrival) for dep, r in results]
    for row in table:
        if sun:
            row["shade_s"] = round(row["duration_s"] - row["sun_exposure_s"], 2)
            row["score"] = round(row["shade_s"] + mu * row["wait_s"], 2)
        else:
            row["score"] = round(row["rhl"] + mu * row["wait_s"], 2)
    feasible = [r for r in table if r["feasible"]]
    pool = feasible or table
    best = min(pool, key=lambda r: (r["score"], r["wait_s"]))
    best["recommended"] = True
    req_row = min(table, key=lambda r: abs((datetime.fromisoformat(r["depart"]) - requested).total_seconds()))
    rec = dict(best)
    rec["constraint_met"] = bool(feasible) or latest_arrival is None
    rec["rhl_saved"] = round(req_row["rhl"] - best["rhl"], 2)
    rec["rhl_saved_pct"] = (
        round(100.0 * (req_row["rhl"] - best["rhl"]) / req_row["rhl"], 1) if req_row["rhl"] else 0.0
    )
    rec["sun_saved_s"] = round(req_row["sun_exposure_s"] - best["sun_exposure_s"], 2)
    rec["wait_min"] = round(best["wait_s"] / 60.0, 1)
    if sun:
        rec["sun_gained_s"] = round(best["sun_exposure_s"] - req_row["sun_exposure_s"], 2)
        rec["sun_gained_pct"] = (
            round(100.0 * rec["sun_gained_s"] / req_row["sun_exposure_s"], 1)
            if req_row["sun_exposure_s"]
            else 0.0
        )

    dep_best = datetime.fromisoformat(best["depart"])
    dep_req = datetime.fromisoformat(req_row["depart"])
    r_best = tdsp.route(ctx, o, d, mode, dep_best, lam, date_key, "balanced", relative=False, **rkw)
    r_req = (
        tdsp.route(ctx, o, d, mode, dep_req, lam, date_key, "balanced", relative=False, **rkw)
        if dep_req != dep_best
        else r_best
    )
    why = explain_change(ctx, tab, r_best, dep_best, dep_req)
    why["route_changed"] = r_best.edges != r_req.edges
    why["from_depart"] = req_row["depart_time"]
    why["to_depart"] = best["depart_time"]
    return DepartureResult(
        table=table,
        recommended=rec,
        requested=req_row,
        why=why,
        date_key=date_key,
        route_recommended=r_best,
        route_requested=r_req,
    )


def explain_change(
    ctx: CityContext,
    tab: SunTable,
    r: tdsp.RouteResult,
    dep_best: datetime,
    dep_ref: datetime,
    threshold: float = SUN_CHANGE_THRESHOLD,
) -> dict[str, Any]:
    """Stretches of route `r` (departing dep_best) whose sun state differs from leaving at dep_ref.

    For each edge: sun at its arrival time when leaving at `dep_best` vs the sun the same edge would
    have had when leaving at `dep_ref` (arrival shifted by the departure difference).
    """
    shift_min = (dep_best - dep_ref).total_seconds() / 60.0
    m_best0 = tab.minute_of(dep_best)
    g = ctx.graph
    flags: list[dict[str, Any] | None] = []
    for seg in r.segments:
        e = seg["edge"]
        if seg["cls"] != "open":
            flags.append(None)
            continue
        m_b = m_best0 + seg["arrival_s"] / 60.0
        m_a = m_b - shift_min
        s_b, s_a = tab.sun(e, m_b), tab.sun(e, m_a)
        if abs(s_b - s_a) >= threshold:
            flags.append(
                {
                    "edge": e,
                    "from_sun": s_a,
                    "to_sun": s_b,
                    "m_a": m_a,
                    "m_b": m_b,
                    "len": float(g.length[e]),
                    "name": seg.get("name") or "unnamed path",
                    "sign": 1 if s_b > s_a else -1,
                }
            )
        else:
            flags.append(None)
    # group consecutive flagged edges with the same street name and direction
    runs: list[list[dict[str, Any]]] = []
    prev_idx = -2
    for idx, f in enumerate(flags):
        if f is None:
            continue
        f = {**f, "_idx": idx}
        if (
            runs
            and prev_idx == idx - 1
            and runs[-1][-1]["name"] == f["name"]
            and runs[-1][-1]["sign"] == f["sign"]
        ):
            runs[-1].append(f)
        else:
            runs.append([f])
        prev_idx = idx
    changes = []
    for run in runs:
        ln = sum(x["len"] for x in run)
        w = [x["len"] / ln for x in run] if ln > 0 else [1.0 / len(run)] * len(run)
        from_sun = sum(wi * x["from_sun"] for wi, x in zip(w, run, strict=True))
        to_sun = sum(wi * x["to_sun"] for wi, x in zip(w, run, strict=True))
        at = _crossing_minute(tab, run[0]["edge"], run[0]["m_a"], run[0]["m_b"])
        changes.append(
            {
                "street": run[0]["name"],
                "from_sun": round(from_sun, 2),
                "to_sun": round(to_sun, 2),
                "at": tab.to_dt(at).strftime("%H:%M"),
                "length_m": round(ln, 1),
                "edges": len(run),
                "direction": "into_shade" if run[0]["sign"] < 0 else "into_sun",
            }
        )
    return {"changes": changes, "threshold": threshold, "shift_min": round(shift_min, 1)}


def _crossing_minute(tab: SunTable, edge: int, m_a: float, m_b: float) -> float:
    """Clock minute between m_a and m_b at which the edge's sun passes the midpoint of its two values."""
    lo, hi = min(m_a, m_b), max(m_a, m_b)
    sa, sb = tab.sun(edge, m_a), tab.sun(edge, m_b)
    mid = 0.5 * (sa + sb)
    t = lo
    prev = tab.sun(edge, t) - mid
    while t < hi:
        t2 = min(hi, t + 1.0)
        cur = tab.sun(edge, t2) - mid
        if prev == 0 or prev * cur <= 0:
            return t2
        t, prev = t2, cur
    return hi

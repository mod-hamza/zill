# ruff: noqa: E501
"""Agent tools (PRD 11.6): JSON-schema'd, deterministic, each returns {ok, data, summary}.

Every successful tool also writes its result into the session's ResultStore under a stable key
(`place.origin`, `route`, `departure`, `weather`, ...) so `{{tokens}}` can be resolved later.
Limits: <= MAX_TOOL_CALLS per turn, TOOL_TIMEOUT_S per call (thread), errors are returned as data.
"""

from __future__ import annotations

import itertools
import json
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from zill import config

from . import policy as policy_mod
from .backend import BackendError, route_arrival
from .session import Session, plan_active_route, plan_summary
from .tokens import HEAVY_KEYS

BREAK_SEARCH_M = 500.0  # max distance to a cool-down stop when plan_day inserts a break
_EXEC = ThreadPoolExecutor(max_workers=8, thread_name_prefix="zill-tool")

Mode = {"type": "string", "enum": ["walk", "cycle", "scooter"]}
PlaceArg = {
    "type": "string",
    "description": "Place name, POI id, or a role already resolved: 'origin'/'dest'.",
}
PrefArg = {
    "type": "string",
    "enum": ["shade", "sun"],
    "description": "shade = least direct sun (default); sun = most direct sun / daylight (well-being). "
    "Defaults to the persona's preference.",
}


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    fn: Callable[[Session, dict[str, Any]], dict[str, Any]]
    internal: bool = False

    def spec(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "parameters": self.parameters}


def ok(data: Any, summary: str) -> dict[str, Any]:
    return {"ok": True, "data": data, "summary": summary}


def fail(msg: str, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "data": {"error": msg, **extra}, "summary": f"Error: {msg}"}


def digest(obj: Any, depth: int = 0) -> Any:
    """Compact, model-facing view of a result: no geometry, rounded floats, short lists."""
    if isinstance(obj, dict):
        return {k: digest(v, depth + 1) for k, v in obj.items() if k not in HEAVY_KEYS}
    if isinstance(obj, list):
        return [digest(v, depth + 1) for v in obj[:8]]
    if isinstance(obj, float):
        return round(obj, 2)
    return obj


# ------------------------------------------------------------------------------------------------
# shared helpers
# ------------------------------------------------------------------------------------------------
def _roles_used(s: Session) -> list[str]:
    placed = s.store.get("place") or {}
    return list(placed.keys())


def _next_role(s: Session) -> str:
    used = _roles_used(s)
    for r in ("origin", "dest"):
        if r not in used:
            return r
    for i in itertools.count(1):
        if f"stop{i}" not in used:
            return f"stop{i}"
    raise AssertionError


def _place(s: Session, arg: Any, mode: str) -> dict[str, Any]:
    if isinstance(arg, dict):
        arg = arg.get("name") or arg.get("query") or arg.get("id") or ""
    arg = str(arg or "").strip()
    if not arg:
        raise BackendError("place is required")
    placed = s.store.get("place") or {}
    if arg in placed:
        return placed[arg]
    low = arg.lower()
    for p in placed.values():
        if low in (str(p.get("name", "")).lower(), str(p.get("id", "")).lower()):
            return p
    return s.backend.resolve_place(arg, mode)


def _mode(s: Session, args: dict[str, Any]) -> str:
    from .personas import get_persona

    m = args.get("mode") or get_persona(s.persona).default_mode
    if m not in ("walk", "cycle", "scooter"):
        raise BackendError(f"unknown mode '{m}'")
    return m


def _pref(s: Session, args: dict[str, Any]) -> str:
    """Routing preference: the tool argument, else the persona's default (daylight seeker = sun)."""
    from .personas import get_persona

    p = args.get("preference") or get_persona(s.persona).preference
    if p not in ("shade", "sun"):
        raise BackendError(f"unknown preference '{p}' (use shade or sun)")
    return p


def _pkw(pref: str) -> dict[str, Any]:
    """Backend kwargs: only sun mode passes `preference`, so shade calls stay exactly as before."""
    return {"preference": "sun"} if pref == "sun" else {}


def best_label(pref: str) -> str:
    return "sunniest" if pref == "sun" else "coolest"


def _when(s: Session, value: Any | None) -> datetime:
    if value in (None, ""):
        return s.clock.now() if s.clock else s.parse_time("13:00")
    try:
        return s.parse_time(value)
    except (ValueError, TypeError) as exc:
        raise BackendError(f"cannot read time '{value}' (use HH:MM or ISO 8601)") from exc


def _latest(s: Session, args: dict[str, Any]) -> datetime | None:
    v = args.get("latest_arrival")
    return _when(s, v) if v else None


def _route_line(r: dict[str, Any]) -> str:
    line = (
        f"{r['label']}: {r['duration_s'] / 60:.1f} min, {r.get('shaded_pct', 0):.0f}% shaded, "
        f"sun {r.get('sun_exposure_s', 0) / 60:.1f} min, RHL {r.get('rhl', 0):.0f}"
    )
    if r.get("sun_gained_s"):
        line += f", sun gained {r['sun_gained_s'] / 60:.1f} min"
    return line


def _new_plan(
    s: Session, kind: str, mode: str, routes: dict[str, Any], origin: dict, dest: dict, **kw: Any
) -> dict:
    pid = s.new_plan_id()
    base = routes.get("fastest") or next(iter(routes.values()))
    plan = {
        "plan_id": pid,
        "kind": kind,
        "persona": s.persona,
        "mode": mode,
        "origin": origin,
        "dest": dest,
        "date_key": s.date_key,
        "depart": base.get("depart"),
        "routes": routes,
        "recommendation": None,
        "status": "draft",
        **kw,
    }
    s.plans[pid] = plan
    s.draft_plan_id = pid
    return plan


def plan_items(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Timed intervals for policy checking (route legs, stops, breaks)."""
    if plan.get("items"):
        return plan["items"]
    r = plan_active_route(plan)
    if not r:
        return []
    return [
        {
            "kind": "leg",
            "label": f"{plan['origin']['name']} to {plan['dest']['name']}",
            "start": r["depart"],
            "end": r["arrive"],
            "sun_exposure_s": r.get("sun_exposure_s", 0.0),
            "outdoor_work": True,
        }
    ]


# ------------------------------------------------------------------------------------------------
# tools
# ------------------------------------------------------------------------------------------------
def t_resolve_place(s: Session, a: dict[str, Any]) -> dict[str, Any]:
    q = a.get("query", "")
    role = a.get("role") or _next_role(s)
    mode = a.get("mode") or "walk"
    try:
        p = s.backend.resolve_place(q, mode)
    except BackendError as exc:
        return fail(str(exc))
    clean = {k: v for k, v in p.items() if k not in HEAVY_KEYS}
    s.store.set(f"place.{role}", clean)
    return ok({"role": role, **clean}, f"Resolved '{q}' as {clean['name']} ({role}).")


def t_get_sun(s: Session, a: dict[str, Any]) -> dict[str, Any]:
    try:
        d = s.backend.sun(_when(s, a.get("at")))
    except BackendError as exc:
        return fail(str(exc))
    s.store.set("sun", d)
    return ok(d, f"Sun altitude {d.get('alt_deg')} deg, azimuth {d.get('az_deg')} deg.")


def t_get_weather(s: Session, a: dict[str, Any]) -> dict[str, Any]:
    at = _when(s, a.get("at"))
    try:
        d = dict(s.backend.weather(at))
    except BackendError as exc:
        return fail(str(exc))
    if "heat_alert" not in d:
        d["heat_alert"] = bool((d.get("apparent_c") or 0) >= 40 or (d.get("uv") or 0) >= 8)
    s.store.set("weather", d)
    src = d.get("source", "unknown source")
    return ok(
        d,
        f"Weather ({src}): apparent {d.get('apparent_c')} C, UV {d.get('uv')}, heat alert {d['heat_alert']}.",
    )


def t_compare_routes(s: Session, a: dict[str, Any]) -> dict[str, Any]:
    try:
        mode = _mode(s, a)
        o, d = _place(s, a.get("origin"), mode), _place(s, a.get("dest"), mode)
        dep = _when(s, a.get("depart_at"))
        pref = _pref(s, a)
        routes = s.backend.routes(o, d, mode, dep, s.date_key, dict(config.LAMBDAS), **_pkw(pref))
    except BackendError as exc:
        return fail(str(exc))
    latest = _latest(s, a)
    key = a.get("store_as") or "route"
    extra = {"preference": "sun"} if pref == "sun" else {}
    plan = _new_plan(
        s,
        "journey",
        mode,
        routes,
        o,
        d,
        latest_arrival=latest.isoformat() if latest else None,
        route_key=key,
        **extra,
    )
    entry = {
        **routes,
        "mode": mode,
        "depart": dep.isoformat(),
        "origin": o["name"],
        "dest": d["name"],
        "plan_id": plan["plan_id"],
        **extra,
    }
    s.store.set(key, entry)
    s.store.set("plan", plan_summary(plan) | {"id": plan["plan_id"]})
    data: dict[str, Any] = {
        "plan_id": plan["plan_id"],
        "stored_as": key,
        "routes": {k: digest(v) for k, v in routes.items()},
    }
    if pref == "sun":  # well-being block for the sunniest route (UV, heat, daylight window, overcast)
        try:
            wb = s.backend.wellbeing(dep, "sun", routes.get("sunniest"))
            s.store.set("wellbeing", wb)
            data.update(preference="sun", wellbeing=digest(wb))
        except Exception as exc:  # well-being context must never break routing
            data["wellbeing_error"] = type(exc).__name__
    labels = ("fastest", "balanced", "sunniest") if pref == "sun" else ("fastest", "balanced", "coolest")
    lines = "; ".join(_route_line(routes[k]) for k in labels if k in routes)
    return ok(data, f"{o['name']} to {d['name']} by {mode} at {dep.strftime('%H:%M')}. {lines}.")


def t_plan_route(s: Session, a: dict[str, Any]) -> dict[str, Any]:
    try:
        mode = _mode(s, a)
        o, d = _place(s, a.get("origin"), mode), _place(s, a.get("dest"), mode)
        dep = _when(s, a.get("depart_at"))
        lam = float(a.get("lambda", config.LAMBDAS["balanced"]))
        if not 0 <= lam <= 10:
            return fail("lambda must be between 0 and 10")
        routes = s.backend.routes(o, d, mode, dep, s.date_key, {"custom": lam}, **_pkw(_pref(s, a)))
    except (BackendError, ValueError) as exc:
        return fail(str(exc))
    r = routes["custom"]
    s.store.set("route.custom", r)
    return ok({"stored_as": "route.custom", "route": digest(r)}, _route_line(r) + ".")


def t_optimise_departure(s: Session, a: dict[str, Any]) -> dict[str, Any]:
    try:
        mode = _mode(s, a)
        o, d = _place(s, a.get("origin"), mode), _place(s, a.get("dest"), mode)
        win = a.get("window") or {}
        start = _when(s, win.get("start"))
        end = _when(s, win.get("end")) if win.get("end") else start + timedelta(minutes=90)
        if end <= start:
            return fail("window end must be after window start")
        pref = _pref(s, a)
        res = s.backend.departure(o, d, mode, start, end, s.date_key, _latest(s, a), **_pkw(pref))
    except BackendError as exc:
        return fail(str(exc))
    best = res["best"]
    if best.get("depart") and best.get("duration_s") is not None and "arrive" not in best:
        best["arrive"] = (
            datetime.fromisoformat(best["depart"]) + timedelta(seconds=best["duration_s"])
        ).isoformat()
    res["window"] = {"start": start.isoformat(), "end": end.isoformat()}
    if pref == "sun":
        res["preference"] = "sun"
    s.store.set("departure", res)
    bt = best.get("depart", "")
    hm = datetime.fromisoformat(bt).strftime("%H:%M") if bt else "?"
    return ok(
        {"stored_as": "departure", **digest(res)},
        f"Best departure {hm} out of {len(res['table'])} evaluated"
        f"{'' if res.get('constraint_met', True) else ' (arrival constraint could not be met)'}.",
    )


def t_find_cool_stops(s: Session, a: dict[str, Any]) -> dict[str, Any]:
    try:
        near = _place(s, a.get("near"), "walk")
    except BackendError as exc:
        return fail(str(exc))
    radius = float(a.get("radius_m", 400))
    items = s.backend.cool_stops(near, radius, a.get("type", "indoor"))
    res = {"items": items, "count": len(items), "nearest": items[0] if items else None, "radius_m": radius}
    s.store.set("stops", res)
    names = ", ".join(i["name"] for i in items[:3]) or "none"
    return ok(
        {"stored_as": "stops", **res},
        f"{len(items)} cool stop(s) within {radius:.0f} m of {near['name']}: {names}.",
    )


def t_check_policy(s: Session, a: dict[str, Any]) -> dict[str, Any]:
    plan = s.plans.get(a.get("plan_id") or s.draft_plan_id or "")
    if plan is None:
        return fail("no plan to check; call compare_routes or plan_day first")
    pack = a.get("policy_pack", "UAE_OUTDOOR_WORK")
    try:
        res = policy_mod.check_policy({"items": plan_items(plan), "persona": s.persona}, pack)
    except KeyError as exc:
        return fail(str(exc))
    res["plan_id"] = plan["plan_id"]
    s.store.set("policy", res)
    return ok(
        {"stored_as": "policy", **res},
        f"{res['label']}: {'no conflicts' if res['ok'] else str(res['count']) + ' conflict(s)'}"
        f"{'' if res['verified'] else ' (pack unverified)'}.",
    )


def t_plan_day(s: Session, a: dict[str, Any]) -> dict[str, Any]:
    """Order stops (permutations up to 6, time-dependent costs), add dwell, insert cool-down breaks."""
    try:
        mode = _mode(s, a)
        raw = a.get("stops") or []
        if not 2 <= len(raw) <= 6:
            return fail("plan_day needs between 2 and 6 stops")
        start = _when(s, a.get("start"))
        stops = []
        for _i, st in enumerate(raw):
            p = _place(s, st.get("place") if isinstance(st, dict) else st, mode)
            stops.append(
                {"place": p, "dwell_min": float(st.get("dwell_min", 10)) if isinstance(st, dict) else 10.0}
            )
        fixed_first = bool(a.get("keep_first", True))
        pkw = _pkw(_pref(s, a))
        cache: dict[tuple[str, str, int], dict[str, Any]] = {}

        def leg(p: dict, q: dict, t: datetime) -> dict[str, Any]:
            k = (p["name"], q["name"], int(t.timestamp() // 600))
            if k not in cache:
                cache[k] = s.backend.routes(
                    p, q, mode, t, s.date_key, {"balanced": config.LAMBDAS["balanced"]}, **pkw
                )["balanced"]
            return cache[k]

        def build(order: list[dict]) -> tuple[list[dict], float]:
            t, items, score, since_break = start, [], 0.0, 0.0
            for i, st in enumerate(order):
                if i > 0:
                    r = leg(order[i - 1]["place"], st["place"], t)
                    t_end = datetime.fromisoformat(r["arrive"])
                    items.append(
                        {
                            "kind": "leg",
                            "label": f"{order[i - 1]['place']['name']} to {st['place']['name']}",
                            "start": r["depart"],
                            "end": r["arrive"],
                            "sun_exposure_s": r.get("sun_exposure_s", 0.0),
                            "rhl": r.get("rhl", 0.0),
                            "route": r,
                            "outdoor_work": True,
                        }
                    )
                    if pkw:  # sun mode: time not in direct sun instead of heat load
                        score += r["duration_s"] + (r["duration_s"] - r.get("sun_exposure_s", 0.0))
                    else:
                        score += r["duration_s"] + r.get("rhl", 0.0)
                    since_break += r.get("rhl", 0.0)
                    t = t_end
                    if since_break > config.RHL_BREAK_THRESHOLD:
                        stop = s.backend.cool_stops(st["place"], BREAK_SEARCH_M, "indoor")
                        if stop:
                            end = t + timedelta(minutes=config.COOL_BREAK_MIN)
                            items.append(
                                {
                                    "kind": "break",
                                    "label": f"Cool-down at {stop[0]['name']}",
                                    "start": t.isoformat(),
                                    "end": end.isoformat(),
                                    "sun_exposure_s": 0.0,
                                    "outdoor_work": False,
                                    "place": stop[0],
                                }
                            )
                            t, since_break = end, 0.0
                end = t + timedelta(minutes=st["dwell_min"])
                crew = s.persona == "crew"
                items.append(
                    {
                        "kind": "work" if crew else "stop",
                        "label": st["place"]["name"],
                        "start": t.isoformat(),
                        "end": end.isoformat(),
                        "sun_exposure_s": st["dwell_min"] * 60.0 if crew else 0.0,
                        "assumed_sun": crew,
                        "outdoor_work": crew,
                    }
                )
                t = end
            return items, score

        head, rest = (stops[:1], stops[1:]) if fixed_first else ([], stops)
        best_items, best_score, best_order = None, float("inf"), None
        for perm in itertools.permutations(rest):
            order = head + list(perm)
            items, score = build(order)
            if score < best_score:
                best_items, best_score, best_order = items, score, order
    except BackendError as exc:
        return fail(str(exc))
    assert best_items is not None and best_order is not None
    legs = [i["route"] for i in best_items if i["kind"] == "leg"]
    pid = s.new_plan_id()
    totals = {
        "duration_s": sum(r["duration_s"] for r in legs),
        "sun_exposure_s": sum(r.get("sun_exposure_s", 0.0) for r in legs),
        "rhl": sum(r.get("rhl", 0.0) for r in legs),
        "breaks": sum(1 for i in best_items if i["kind"] == "break"),
        "end": best_items[-1]["end"],
    }
    plan = {
        "plan_id": pid,
        "kind": "day",
        "persona": s.persona,
        "mode": mode,
        "origin": best_order[0]["place"],
        "dest": best_order[-1]["place"],
        "date_key": s.date_key,
        "depart": start.isoformat(),
        "routes": {"balanced": legs[-1]} if legs else {},
        "recommendation": "balanced" if legs else None,
        "items": best_items,
        "order": [o["place"]["name"] for o in best_order],
        "status": "draft",
    }
    s.plans[pid] = plan
    s.draft_plan_id = pid
    pub = {
        "plan_id": pid,
        "order": plan["order"],
        "totals": totals,
        "items": [{k: v for k, v in i.items() if k != "route"} for i in best_items],
    }
    s.store.set("day", {**pub, "plan_id": pid})
    return ok(
        {"stored_as": "day", **pub},
        f"Day plan {' -> '.join(plan['order'])}; {totals['breaks']} cool-down break(s).",
    )


def t_commit_plan(s: Session, a: dict[str, Any]) -> dict[str, Any]:
    pid = a.get("plan_id") or s.draft_plan_id
    if pid not in s.plans:
        return fail(f"unknown plan '{pid}'")
    if s.autonomy == 1:
        return ok(
            {"plan_id": pid, "status": "advisor_only"},
            "Advisor level: suggestions only, nothing is committed.",
        )
    return ok(
        {"plan_id": pid, "status": "awaiting_approval"},
        f"{pid} is queued for the user's approval; it is not committed yet.",
    )


def t_simulate_clock(s: Session, a: dict[str, Any]) -> dict[str, Any]:
    try:
        ts = _when(s, a.get("ts"))
    except BackendError as exc:
        return fail(str(exc))
    s.clock.jump(ts)
    return ok({"sim_time": ts.isoformat()}, f"Simulated clock set to {ts.strftime('%H:%M')}.")


def t_get_active_plan(s: Session, a: dict[str, Any]) -> dict[str, Any]:
    p = s.active_plan
    if not p:
        return ok({"active": None}, "No committed plan.")
    return ok({"active": plan_summary(p)}, f"Active plan {p['plan_id']} ({p.get('mode')}).")


def t_explain_segment(s: Session, a: dict[str, Any]) -> dict[str, Any]:
    plan = s.plans.get(a.get("plan_id") or s.draft_plan_id or "")
    if plan is None:
        return fail("no plan to explain")
    label = a.get("route") or best_label(plan.get("preference", "shade"))
    r = plan["routes"].get(label)
    if r is None:
        return fail(f"plan has no '{label}' route")
    try:
        d = s.backend.explain_segment(r, int(a.get("segment_index", 0)), plan["date_key"])
    except BackendError as exc:
        return fail(str(exc))
    s.store.set("segment", d)
    return ok({"stored_as": "segment", **digest(d)}, f"Segment explained ({label}).")


def t_build_city(s: Session, a: dict[str, Any]) -> dict[str, Any]:
    d = s.backend.city_summary()
    d["query"] = a.get("query", "")
    d["note"] = (
        "Non-destructive: the city is already baked; the recorded build log is replayed, labelled cached."
    )
    s.store.set("city", d)
    return ok(
        {"stored_as": "city", **d}, f"City {d.get('name') or d['city_id']} is already baked (cached build)."
    )


def _tools() -> list[Tool]:
    T = Tool
    obj = lambda props, req=(): {"type": "object", "properties": props, "required": list(req)}  # noqa: E731
    return [
        T(
            "resolve_place",
            "Resolve a place name to a point on the street network. Call once per place.",
            obj(
                {
                    "query": {"type": "string"},
                    "role": {"type": "string", "description": "origin | dest | stop1.."},
                    "mode": Mode,
                },
                ["query"],
            ),
            t_resolve_place,
        ),
        T(
            "get_sun",
            "Sun altitude/azimuth and sunrise/sunset for a time (ISO or HH:MM on the session date).",
            obj({"at": {"type": "string"}}),
            t_get_sun,
        ),
        T(
            "get_weather",
            "Apparent temperature, UV and heat-alert flag at a time (with data source).",
            obj({"at": {"type": "string"}}),
            t_get_weather,
        ),
        T(
            "plan_route",
            "One route at a chosen coolness lambda (0 fastest, 1 balanced, 3 coolest).",
            obj(
                {
                    "origin": PlaceArg,
                    "dest": PlaceArg,
                    "mode": Mode,
                    "depart_at": {"type": "string"},
                    "lambda": {"type": "number"},
                    "preference": PrefArg,
                },
                ["origin", "dest"],
            ),
            t_plan_route,
        ),
        T(
            "compare_routes",
            "Compute Fastest, Balanced and Coolest routes (or, with preference sun, Fastest, Balanced and "
            "Sunniest plus a well-being block) with computed stats. Creates a draft plan.",
            obj(
                {
                    "origin": PlaceArg,
                    "dest": PlaceArg,
                    "mode": Mode,
                    "depart_at": {"type": "string"},
                    "latest_arrival": {"type": "string"},
                    "store_as": {"type": "string"},
                    "preference": PrefArg,
                },
                ["origin", "dest"],
            ),
            t_compare_routes,
        ),
        T(
            "optimise_departure",
            "Evaluate balanced routes over a departure window (5 min steps) and recommend the best time.",
            obj(
                {
                    "origin": PlaceArg,
                    "dest": PlaceArg,
                    "mode": Mode,
                    "window": obj({"start": {"type": "string"}, "end": {"type": "string"}}),
                    "latest_arrival": {"type": "string"},
                    "preference": PrefArg,
                },
                ["origin", "dest"],
            ),
            t_optimise_departure,
        ),
        T(
            "find_cool_stops",
            "Nearby indoor / air-conditioned stops (malls, hotels, metro, cafes).",
            obj(
                {
                    "near": PlaceArg,
                    "radius_m": {"type": "number"},
                    "type": {
                        "type": "string",
                        "enum": ["indoor", "mall", "cafe", "hotel", "metro", "park", "water"],
                    },
                },
                ["near"],
            ),
            t_find_cool_stops,
        ),
        T(
            "plan_day",
            "Order up to 6 stops with dwell times, route between them and insert cool-down breaks.",
            obj(
                {
                    "stops": {
                        "type": "array",
                        "items": obj({"place": PlaceArg, "dwell_min": {"type": "number"}}, ["place"]),
                    },
                    "mode": Mode,
                    "start": {"type": "string"},
                    "keep_first": {"type": "boolean"},
                    "preference": PrefArg,
                },
                ["stops"],
            ),
            t_plan_day,
        ),
        T(
            "check_policy",
            "Check a plan against a policy pack (UAE_OUTDOOR_WORK midday break; unverified v1).",
            obj({"plan_id": {"type": "string"}, "policy_pack": {"type": "string"}}),
            t_check_policy,
        ),
        T(
            "commit_plan",
            "Request commitment of a plan. Needs the user's approval at autonomy L2/L3; advisor L1 never commits.",
            obj({"plan_id": {"type": "string"}}),
            t_commit_plan,
        ),
        T("get_active_plan", "The currently committed plan, if any.", obj({}), t_get_active_plan),
        T(
            "explain_segment",
            "Why a segment of a route is shaded or sunny (casting building and time window when known).",
            obj(
                {
                    "plan_id": {"type": "string"},
                    "route": {"type": "string"},
                    "segment_index": {"type": "integer"},
                }
            ),
            t_explain_segment,
        ),
        T(
            "build_city",
            "Show that the city is built (non-destructive; replays the recorded build log).",
            obj({"query": {"type": "string"}}),
            t_build_city,
        ),
        T(
            "simulate_clock",
            "Internal: jump the simulated clock.",
            obj({"ts": {"type": "string"}}, ["ts"]),
            t_simulate_clock,
            internal=True,
        ),
    ]


REGISTRY: dict[str, Tool] = {t.name: t for t in _tools()}


def planner_specs() -> list[dict[str, Any]]:
    return [t.spec() for t in REGISTRY.values() if not t.internal]


def execute(s: Session, name: str, args: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Run one tool with a timeout and the per-turn call cap. Returns (result, duration_ms)."""
    t0 = time.perf_counter()
    tool = REGISTRY.get(name)
    if tool is None or tool.internal and name != "simulate_clock":
        return fail(f"unknown tool '{name}'"), 0
    if s.calls_this_turn >= config.MAX_TOOL_CALLS:
        return fail(
            f"tool-call limit reached ({config.MAX_TOOL_CALLS} per turn); finish with what you have"
        ), 0
    s.calls_this_turn += 1
    if not isinstance(args, dict):
        return fail("arguments must be an object"), 0
    fut = _EXEC.submit(tool.fn, s, args)
    try:
        res = fut.result(timeout=config.TOOL_TIMEOUT_S)
    except FutureTimeout:
        res = fail(f"{name} timed out after {config.TOOL_TIMEOUT_S} s")
    except Exception as exc:  # errors are data, never crashes
        res = fail(f"{name} failed ({type(exc).__name__}: {exc})")
    return res, int((time.perf_counter() - t0) * 1000)


def model_view(s: Session, res: dict[str, Any]) -> str:
    """JSON the model sees for a tool result: summary, compact data, usable token paths."""
    out: dict[str, Any] = {"ok": res["ok"], "summary": res["summary"], "data": digest(res["data"])}
    key = res["data"].get("stored_as") if isinstance(res["data"], dict) else None
    if res["ok"] and key:
        out["token_paths"] = s.store.token_paths(key, limit=48)
    elif res["ok"] and isinstance(res["data"], dict) and res["data"].get("role"):
        out["token_paths"] = [f"place.{res['data']['role']}.name"]
    return json.dumps(out, default=str)


__all__ = ["REGISTRY", "execute", "planner_specs", "model_view", "digest", "plan_items", "route_arrival"]

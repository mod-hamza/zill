"""Routing endpoints: /api/route, /api/departure, /api/plan, /api/scenarios (PRD 10)."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter

from zill import config
from zill.api.common import ORJSON, ApiError
from zill.api.schemas import (
    DepartureRequest,
    DepartureResponse,
    PlanRequest,
    PlanResponse,
    RouteRequest,
    RouteResponse,
    SunRouteResponse,
)
from zill.routing import tdsp
from zill.routing.departure import optimise_departure
from zill.services import CityContext, get_city

router = APIRouter(prefix="/api", tags=["routing"], default_response_class=ORJSON)
log = logging.getLogger(__name__)

DEFAULT_DATE_KEY = "summer"


def resolve_times(ctx: CityContext, depart_at: str | None, date_key: str | None) -> tuple[datetime, str]:
    """(aware departure datetime, date_key). `depart_at` is ISO or HH:MM (needs/uses date_key)."""
    tz = ZoneInfo(ctx.tz)
    if depart_at is None:
        raise ApiError(422, "bad_time", "depart_at is required")
    s = depart_at.strip()
    try:
        if len(s) <= 5 and ":" in s:
            dk = date_key or DEFAULT_DATE_KEY
            dt = ctx.at(dk, s)
        else:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            dt = dt.replace(tzinfo=tz) if dt.tzinfo is None else dt.astimezone(tz)
            dk = date_key or dt.date().isoformat()
    except ValueError:
        raise ApiError(
            422, "bad_time", f"Could not parse time {depart_at!r}; use ISO-8601 or HH:MM"
        ) from None
    try:
        dk = ctx.date_for(dk)[0]  # an ISO date that is a preset maps to the preset id
    except Exception:
        raise ApiError(422, "bad_date", f"Unknown date key {dk!r}; use a preset id or YYYY-MM-DD") from None
    return dt, dk


def _place_model(p: dict[str, Any]) -> dict[str, Any]:
    return p


def _lambdas(req_l: list[float] | None) -> tuple[float, float, float]:
    if not req_l:
        lm = config.LAMBDAS
        return float(lm["fastest"]), float(lm["balanced"]), float(lm["coolest"])
    if len(req_l) != 3 or any(x < 0 for x in req_l):
        raise ApiError(
            422, "bad_lambdas", "lambdas must be three non-negative numbers [fastest, balanced, coolest]"
        )
    return float(req_l[0]), float(req_l[1]), float(req_l[2])


def _place_in(p: Any) -> Any:
    return p.model_dump(exclude_none=True) if hasattr(p, "model_dump") else p


def wellbeing_for(
    ctx: CityContext, preference: str, dep: datetime, best: tdsp.RouteResult
) -> dict[str, Any] | None:
    """`wellbeing` block for the recommended route. Never fails the route: errors -> None (logged)."""
    try:
        from zill import weather, wellbeing
        from zill.sun.position import sun_position

        o = ctx.origin
        alt = sun_position(dep, o["lat"], o["lon"], ctx.tz).alt_deg
        w = weather.get(ctx.city_id, dep, prefer_recorded=True)
        return wellbeing.assess(preference, alt, w, best.stats, best.segments)
    except Exception as e:  # weather/sun lookups must never break routing
        log.warning("wellbeing unavailable: %s", type(e).__name__)
        return None


@router.post("/route", response_model=RouteResponse | SunRouteResponse, response_model_by_alias=True)
def post_route(req: RouteRequest) -> dict[str, Any]:
    """Fastest / Balanced / Coolest routes with stats and per-segment geometry (CONTRACTS 5).

    `preference: "sun"` returns fastest / balanced / sunniest instead of coolest. Both modes add
    `best` (= coolest or sunniest), `preference` and a `wellbeing` block (UV, heat stress, daylight
    window, break prompts, overcast note)."""
    t0 = time.perf_counter()
    ctx = get_city(req.city)
    dep, dk = resolve_times(ctx, req.depart_at, req.date_key)
    o = ctx.resolve_place(_place_in(req.origin), req.mode)
    d = ctx.resolve_place(_place_in(req.dest), req.mode)
    res = tdsp.compare(
        ctx,
        o["node"],
        d["node"],
        req.mode,
        dep,
        dk,
        _lambdas(req.lambdas),
        with_geometry=req.include_segments,
        preference=req.preference,
    )
    best = res[tdsp.best_label(req.preference)]
    out = {k: v.to_dict(include_segments=req.include_segments) for k, v in res.items()}
    return {
        **out,
        "best": out[tdsp.best_label(req.preference)],
        "preference": req.preference,
        "origin": o,
        "dest": d,
        "date_key": dk,
        "wellbeing": wellbeing_for(ctx, req.preference, dep, best),
        "timing_ms": round((time.perf_counter() - t0) * 1000, 1),
    }


@router.post("/departure", response_model=DepartureResponse)
def post_departure(req: DepartureRequest) -> dict[str, Any]:
    """Best departure in a window (Balanced route per departure, minimises RHL + mu*wait) with a `why`.

    Sun mode minimises shade_s + mu*wait (most direct sun) instead."""
    t0 = time.perf_counter()
    ctx = get_city(req.city)
    w = req.window
    start_s = (w.start if w and w.start else None) or req.depart_at
    start, dk = resolve_times(ctx, start_s, req.date_key)
    end = start + timedelta(minutes=90)
    if w and w.end:
        end, _ = resolve_times(ctx, w.end, dk)
    if end < start:
        raise ApiError(422, "bad_window", "window end is before window start")
    if (end - start) > timedelta(hours=6):
        raise ApiError(422, "bad_window", "window longer than 6 hours")
    latest = resolve_times(ctx, req.latest_arrival, dk)[0] if req.latest_arrival else None
    requested = start
    if req.depart_at and w and w.start:
        requested, _ = resolve_times(ctx, req.depart_at, dk)
    o = ctx.resolve_place(_place_in(req.origin), req.mode)
    d = ctx.resolve_place(_place_in(req.dest), req.mode)
    res = optimise_departure(
        ctx,
        o["node"],
        d["node"],
        req.mode,
        start,
        end,
        step_min=req.step_min,
        latest_arrival=latest,
        mu=req.mu,
        date_key=dk,
        requested=requested,
        preference=req.preference,
    )
    out = res.to_dict()
    out.update(
        origin=o,
        dest=d,
        preference=req.preference,
        timing_ms=round((time.perf_counter() - t0) * 1000, 1),
    )
    return out


@router.post("/plan", response_model=PlanResponse)
def post_plan(req: PlanRequest) -> dict[str, Any]:
    """Multi-stop day / shift planner (P1): ordering, cool-down breaks, policy conflicts."""
    from zill.routing import planner

    ctx = get_city(req.city)
    start_at, dk = resolve_times(ctx, req.start_at, req.date_key)
    if not 1 <= len(req.stops) <= 8:
        raise ApiError(422, "bad_stops", "between 1 and 8 stops are supported")
    return planner.plan_from_request(ctx, req, start_at, dk)


def scenarios_path(city: str) -> Path:
    base = Path(os.environ.get("ZILL_SCENARIOS_DIR") or (config.DATA_DIR / "scenarios"))
    return base / ("hero.json" if city == config.DEFAULT_CITY else f"hero_{city}.json")


@router.get("/scenarios/{city}")
def get_scenarios(city: str) -> Any:
    get_city(city)
    p = scenarios_path(city)
    if not p.exists():
        return {"city_id": city, "scenarios": [], "generated": False}  # valid, empty: no console 404
    return json.loads(p.read_text(encoding="utf-8"))

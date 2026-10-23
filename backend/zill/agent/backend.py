"""Adapter between the agent tools and the engine modules (CONTRACTS 4).

Tools never import routing/shade/weather directly; they call a `ToolBackend`. `ServicesBackend` is the
real implementation over `zill.services`; tests inject a deterministic synthetic backend.
All route dicts handed to tools are *normalised*: CONTRACTS 5 shape plus the stats hoisted to the top
level (so `{{route.coolest.sun_saved_min}}` resolves) and `arrive` / `label` / `lambda` fields.
"""

from __future__ import annotations

import dataclasses
import inspect
import math
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from zill import config

STAT_KEYS = (
    "distance_m",
    "duration_s",
    "sun_exposure_s",
    "shaded_pct",
    "covered_pct",
    "indoor_pct",
    "rhl",
    "added_time_s",
    "sun_saved_s",
    "sun_saved_pct",
    "rhl_saved_pct",
    "sun_gained_s",  # sun mode only (hoisted when present)
    "sun_gained_pct",
)
SUN_KEYS = ("fastest", "balanced", "sunniest")


class BackendError(Exception):
    """A tool-visible failure (becomes `{ok:false}` data, never a crash)."""


def as_dict(obj: Any) -> dict[str, Any]:
    if isinstance(obj, dict):
        return obj
    for attr in ("to_dict", "model_dump", "dict"):
        fn = getattr(obj, attr, None)
        if callable(fn):
            return fn()
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)  # type: ignore[arg-type]
    return dict(vars(obj))


def normalise_route(raw: Any, label: str | None = None, mode: str | None = None) -> dict[str, Any]:
    """CONTRACTS 5 route -> agent route (stats hoisted, arrival computed)."""
    r = dict(as_dict(raw))
    stats = dict(r.get("stats") or {})
    out = dict(r)
    for k in STAT_KEYS:
        if k in stats:
            out[k] = stats[k]
    out["stats"] = stats
    if label:
        out["label"] = label
    if mode:
        out["mode"] = mode
    if r.get("lambda") is not None:
        out["lam"] = r["lambda"]
    dep = r.get("depart")
    if isinstance(dep, str) and "duration_s" in out:
        out["arrive"] = (
            datetime.fromisoformat(dep) + timedelta(seconds=float(out["duration_s"]))
        ).isoformat()
    out.setdefault("added_time_s", 0.0)
    return out


def route_arrival(route: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(route["arrive"])


class ToolBackend(ABC):
    """Everything a tool may ask of the engine."""

    city_id: str = config.DEFAULT_CITY
    tz: str = config.TIMEZONE

    @abstractmethod
    def resolve_place(self, query: str, mode: str = "walk") -> dict[str, Any]: ...

    @abstractmethod
    def date_obj(self, date_key: str) -> datetime: ...

    @abstractmethod
    def routes(
        self,
        origin: dict[str, Any],
        dest: dict[str, Any],
        mode: str,
        depart: datetime,
        date_key: str,
        lams: dict[str, float],
        blocked_edges: frozenset[int] = frozenset(),
    ) -> dict[str, dict[str, Any]]:
        """label -> normalised route. Raises BackendError when no route exists."""

    @abstractmethod
    def departure(
        self,
        origin: dict[str, Any],
        dest: dict[str, Any],
        mode: str,
        start: datetime,
        end: datetime,
        date_key: str,
        latest_arrival: datetime | None,
    ) -> dict[str, Any]: ...

    @abstractmethod
    def sun(self, at: datetime) -> dict[str, Any]: ...

    @abstractmethod
    def weather(self, at: datetime) -> dict[str, Any]: ...

    @abstractmethod
    def cool_stops(self, near: dict[str, Any], radius_m: float, kind: str) -> list[dict[str, Any]]: ...

    @abstractmethod
    def explain_segment(self, route: dict[str, Any], segment: int, date_key: str) -> dict[str, Any]: ...

    @abstractmethod
    def validate_route(self, route: dict[str, Any], mode: str) -> list[str]:
        """Defects (empty = every edge is valid for the mode)."""

    def city_summary(self) -> dict[str, Any]:
        return {"city_id": self.city_id}

    def wellbeing(self, at: datetime, preference: str, route: dict[str, Any] | None) -> dict[str, Any]:
        """Well-being block (UV, heat stress, daylight window, breaks, overcast) for a route at `at`."""
        from zill import wellbeing as wb

        sun = self.sun(at)
        w = dict(self.weather(at))
        w.setdefault("uv_index", w.get("uv"))
        r = route or {}
        return wb.assess(preference, sun.get("alt_deg"), w, r.get("stats") or r, r.get("segments"))


# ------------------------------------------------------------------------------------------------
# Real implementation
# ------------------------------------------------------------------------------------------------
_COOL_KINDS = {
    "indoor": {"mall", "hotel", "metro", "cafe", "museum", "station"},
    "mall": {"mall"},
    "cafe": {"cafe"},
    "hotel": {"hotel"},
    "metro": {"metro", "station"},
    "water": {"water"},
    "park": {"park"},
}


class ServicesBackend(ToolBackend):
    def __init__(self, city_id: str | None = None) -> None:
        self.city_id = city_id or config.DEFAULT_CITY

    def warm(self, block: bool = False) -> None:
        """Pre-compile the sun/weather path (first call can take ~9 s, over the 8 s tool timeout)."""
        import threading

        def work() -> None:
            try:
                self.weather(self.date_obj("summer").replace(hour=13))
            except Exception:
                pass

        if block:
            work()
        else:
            threading.Thread(target=work, daemon=True, name="zill-warm").start()

    # -- context ------------------------------------------------------------------------------
    @property
    def ctx(self) -> Any:
        from zill import services

        return services.get_city(self.city_id)

    @property
    def tz(self) -> str:  # type: ignore[override]
        return self.ctx.tz

    def date_obj(self, date_key: str) -> datetime:
        d = self.ctx.date_obj(date_key)
        return datetime(d.year, d.month, d.day, tzinfo=ZoneInfo(self.ctx.tz))

    def city_summary(self) -> dict[str, Any]:
        m = self.ctx.meta
        return {
            "city_id": self.city_id,
            "name": m.get("name"),
            "buildings": m.get("counts", {}).get("buildings"),
            "edges": m.get("counts", {}).get("edges"),
            "attribution": m.get("attribution"),
            "build_log_steps": len(m.get("build_log", [])),
        }

    # -- places -------------------------------------------------------------------------------
    def resolve_place(self, query: str, mode: str = "walk") -> dict[str, Any]:
        from difflib import SequenceMatcher

        ctx = self.ctx
        q = (query or "").strip().lower()
        if not q:
            raise BackendError("empty place query")
        best, best_score = None, 0.0
        qtok = set(q.replace(",", " ").split())
        for p in ctx.pois:
            name = p["name"].lower()
            if q == p["id"].lower() or q == name:
                best, best_score = p, 2.0
                break
            ntok = set(name.replace(",", " ").split())
            overlap = len(qtok & ntok) / max(len(qtok), 1)
            sub = 1.0 if (q in name or name in q) else 0.0
            score = 0.6 * overlap + 0.3 * sub + 0.1 * SequenceMatcher(None, q, name).ratio()
            if score > best_score:
                best, best_score = p, score
        if best is None or best_score < 0.35:
            raise BackendError(f"no place matches '{query}'")
        try:
            placed = ctx.resolve_place({"poi": best["id"]}, mode)
        except Exception as exc:
            raise BackendError(f"cannot place '{best['name']}' on the {mode} network: {exc}") from exc
        placed.update({"id": best["id"], "kind": best.get("kind"), "name": best["name"]})
        return placed

    # -- routing ------------------------------------------------------------------------------
    def routes(  # type: ignore[override]
        self, origin, dest, mode, depart, date_key, lams, blocked_edges=frozenset(), preference="shade"
    ):
        try:
            from zill.routing import tdsp as tdsp_mod
            from zill.routing.tdsp import route as route_fn
        except ImportError as exc:
            raise BackendError("routing engine not available") from exc
        ctx = self.ctx
        kwargs: dict[str, Any] = {}
        if blocked_edges and "blocked_edges" in inspect.signature(route_fn).parameters:
            kwargs["blocked_edges"] = blocked_edges
        elif blocked_edges:
            raise BackendError("routing engine does not support closures")
        out: dict[str, dict[str, Any]] = {}
        sun = preference == "sun"
        if sun:
            kwargs["preference"] = "sun"
        try:
            if set(lams) == {"fastest", "balanced", "coolest"} and hasattr(tdsp_mod, "compare"):
                kw2: dict[str, Any] = {"blocked_edges": blocked_edges} if blocked_edges else {}
                if sun:
                    kw2["preference"] = "sun"
                res = tdsp_mod.compare(
                    ctx, origin["node"], dest["node"], mode, depart, date_key,
                    (lams["fastest"], lams["balanced"], lams["coolest"]), **kw2,
                )
                keys = SUN_KEYS if sun else ("fastest", "balanced", "coolest")
                return {k: normalise_route(res[k], k, mode) for k in keys}
            for label in sorted(lams, key=lambda k: lams[k]):
                res1 = route_fn(
                    ctx, origin["node"], dest["node"], mode, depart, lams[label], date_key, **kwargs
                )
                out[label] = normalise_route(res1, label, mode)
        except Exception as exc:
            raise BackendError(f"no {mode} route found ({type(exc).__name__}: {exc})") from exc
        return out

    def departure(self, origin, dest, mode, start, end, date_key, latest_arrival, preference="shade"):  # type: ignore[override]
        try:
            from zill.routing.departure import optimise_departure
        except ImportError as exc:
            raise BackendError("departure optimiser not available") from exc
        try:
            res = as_dict(
                optimise_departure(
                    self.ctx,
                    origin["node"],
                    dest["node"],
                    mode,
                    start,
                    end,
                    step_min=config.DEPARTURE_STEP_MIN,
                    latest_arrival=latest_arrival,
                    mu=config.DEPARTURE_MU,
                    date_key=date_key,
                    requested=start,
                    **({"preference": "sun"} if preference == "sun" else {}),
                )
            )
        except Exception as exc:
            raise BackendError(f"departure optimiser failed ({type(exc).__name__}: {exc})") from exc
        return normalise_departure(res)

    # -- context tools ------------------------------------------------------------------------
    def sun(self, at):  # type: ignore[override]
        from zill.sun.position import sun_position, sun_times

        o = self.ctx.origin
        sp = sun_position(at, o["lat"], o["lon"], self.ctx.tz)
        t = sun_times(at.date(), o["lat"], o["lon"], self.ctx.tz)
        out = {"at": at.isoformat(), "alt_deg": round(sp.alt_deg, 1), "az_deg": round(sp.az_deg, 1)}
        for k, v in t.items():
            out[k] = v.isoformat() if hasattr(v, "isoformat") else v
        return out

    def weather(self, at):  # type: ignore[override]
        try:
            from zill import weather as W
        except ImportError as exc:
            raise BackendError("weather module not available") from exc
        fn = getattr(W, "get", None)
        if fn is None:
            raise BackendError("weather module has no get()")
        try:
            res = as_dict(fn(self.city_id, at))
        except Exception as exc:
            raise BackendError(f"weather unavailable ({type(exc).__name__})") from exc
        return normalise_weather(res)

    def wellbeing(self, at, preference, route):  # type: ignore[override]
        """Real engine: recorded weather first for the date (no network wait), then live."""
        from zill import weather as W
        from zill import wellbeing as wb
        from zill.sun.position import sun_position

        o = self.ctx.origin
        alt = sun_position(at, o["lat"], o["lon"], self.ctx.tz).alt_deg
        w = W.get(self.city_id, at, prefer_recorded=True)
        r = route or {}
        return wb.assess(preference, alt, w, r.get("stats") or r, r.get("segments"))

    def cool_stops(self, near, radius_m, kind):  # type: ignore[override]
        kinds = _COOL_KINDS.get(kind, _COOL_KINDS["indoor"])
        out = []
        for p in self.ctx.pois:
            if p.get("kind") not in kinds:
                continue
            d = math.hypot(p["x"] - near["x"], p["z"] - near["z"])
            if d <= radius_m and p.get("id") != near.get("id") and p["name"] != near.get("name"):
                out.append(
                    {
                        "id": p["id"],
                        "name": p["name"],
                        "kind": p.get("kind"),
                        "distance_m": round(d, 0),
                        "lat": p["lat"],
                        "lon": p["lon"],
                    }
                )
        out.sort(key=lambda s: s["distance_m"])
        return out[:5]

    def explain_segment(self, route, segment, date_key):  # type: ignore[override]
        segs = route.get("segments") or []
        if not 0 <= segment < len(segs):
            raise BackendError(f"segment {segment} out of range (route has {len(segs)})")
        seg = segs[segment]
        geom = seg.get("geometry") or []
        out: dict[str, Any] = {
            "edge": seg["edge"],
            "street": seg.get("name"),
            "class": seg.get("cls"),
            "sun_fraction": seg.get("sun"),
            "caster": None,
        }
        if not geom or seg.get("cls") != "open":
            out["note"] = (
                "covered or indoor segment: no direct sun to explain" if seg.get("cls") != "open" else ""
            )
            return out
        mid = geom[len(geom) // 2]
        ts = datetime.fromisoformat(route["depart"]) + timedelta(seconds=float(seg.get("arrival_s") or 0.0))
        out["at"] = ts.isoformat()
        try:
            from zill.shade.explain import casting_building
            from zill.sun.position import sun_position

            o = self.ctx.origin
            sp = sun_position(ts, o["lat"], o["lon"], self.ctx.tz)
            out["caster"] = casting_building(
                self.city_id, float(mid[0]), float(mid[1]), sp.alt_deg, sp.az_deg
            )
        except Exception:
            out["note"] = "casting building lookup unavailable"
        return out

    def validate_route(self, route, mode):  # type: ignore[override]
        g = self.ctx.graph
        allowed = g.allowed.get(mode) if hasattr(g, "allowed") else None
        defects = []
        for e in route.get("edges", []):
            if allowed is not None and not bool(allowed[e]):
                defects.append(f"edge {e} is not traversable by {mode}")
            elif mode in ("cycle", "scooter") and bool(g.stairs[e]):
                defects.append(f"edge {e} has stairs; forbidden for {mode}")
        return defects


def normalise_departure(res: dict[str, Any]) -> dict[str, Any]:
    """DepartureResult (routing.departure) -> {best, first(requested), table, why, rhl_saved_pct, wait_min}.

    Also tolerates the older shape {table, recommendation|best, why[]}.
    """
    table = res.get("table") or res.get("rows") or res.get("departures") or []
    best = dict(res.get("recommended") or res.get("recommendation") or res.get("best") or {})
    if not best and table:
        best = dict(min(table, key=lambda r: r.get("rhl", 1e18)))
    first = dict(res.get("requested") or (table[0] if table else best))
    out: dict[str, Any] = {"best": best, "first": first, "table": table, "why": res.get("why") or {}}
    if best.get("rhl_saved_pct") is not None:
        out["rhl_saved_pct"] = best["rhl_saved_pct"]
    elif best.get("rhl") is not None and first.get("rhl"):
        out["rhl_saved_pct"] = 100.0 * (first["rhl"] - best["rhl"]) / first["rhl"]
    if best.get("wait_s") is not None:
        out["wait_s"] = best["wait_s"]
    elif best.get("depart") and first.get("depart"):
        out["wait_s"] = (
            datetime.fromisoformat(best["depart"]) - datetime.fromisoformat(first["depart"])
        ).total_seconds()
    if best.get("constraint_met") is False:
        out["constraint_met"] = False
    if best.get("sun_gained_s") is not None:  # sun mode
        out["sun_gained_s"] = best["sun_gained_s"]
        out["sun_gained_pct"] = best.get("sun_gained_pct")
    return out


def normalise_weather(res: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in res.items() if k != "hourly"}
    for src, dst in (
        ("apparent_temperature", "apparent_c"),
        ("apparent_temp_c", "apparent_c"),
        ("temperature", "temp_c"),
        ("temperature_2m", "temp_c"),
        ("uv_index", "uv"),
    ):
        if src in out and dst not in out:
            out[dst] = out[src]
    return out

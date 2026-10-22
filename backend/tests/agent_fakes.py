"""Deterministic synthetic ToolBackend for agent tests (no baked city required).

Two corridors between every pair of places: a direct 'boulevard' (edges 1,2,3; open, fast) and an
'arcade' (edges 4,5,6; covered, 12% longer). Sun exposure follows a bell around 13:30 so shade and
RHL depend on the clock, like the real engine. Closures of edges force the other corridor.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from zill.agent.backend import BackendError, ToolBackend, normalise_departure, normalise_route

TZ = ZoneInfo("Asia/Dubai")
SPEED = {"walk": 1.4, "cycle": 4.5, "scooter": 5.0}
PLACES = {
    "metro": ("metro_station", "Burj Khalifa Metro Station", 0.0, 0.0, "metro"),
    "opera": ("dubai_opera", "Dubai Opera", 900.0, 100.0, "landmark"),
    "mall": ("dubai_mall", "The Dubai Mall", 450.0, -300.0, "mall"),
    "hotel": ("address_hotel", "Address Downtown", 1200.0, 500.0, "hotel"),
}
DIRECT, ARCADE = [1, 2, 3], [4, 5, 6]


def bell(minute: float) -> float:
    return math.exp(-((((minute / 60.0) - 13.5) / 2.2) ** 2))


class SyntheticBackend(ToolBackend):
    city_id = "synthetic"
    tz = "Asia/Dubai"

    def __init__(self, stairs_edges: set[int] | None = None) -> None:
        self.places: dict[str, dict[str, Any]] = {}
        for i, (key, (pid, name, x, z, kind)) in enumerate(PLACES.items()):
            self.places[key] = {
                "id": pid,
                "name": name,
                "x": x,
                "z": z,
                "lat": 25.19 + z * 1e-5,
                "lon": 55.27 + x * 1e-5,
                "node": i,
                "kind": kind,
                "snap_m": 3.0,
            }
        self.stairs = stairs_edges or set()
        self.route_calls = 0

    # -- required API ----------------------------------------------------------------------
    def date_obj(self, date_key: str) -> datetime:
        iso = {"summer": "2026-07-15", "winter": "2026-01-15", "hackathon": "2026-10-24"}.get(
            date_key, date_key
        )
        d = datetime.fromisoformat(iso)
        return d.replace(tzinfo=TZ)

    def resolve_place(self, query: str, mode: str = "walk") -> dict[str, Any]:
        q = query.strip().lower()
        for key, p in self.places.items():
            if q in (key, p["id"], p["name"].lower()) or key in q:
                return dict(p)
        raise BackendError(f"no place matches '{query}'")

    def _raw(
        self, o: dict, d: dict, mode: str, depart: datetime, corridor: str, lam: float
    ) -> dict[str, Any]:
        dist = math.hypot(o["x"] - d["x"], o["z"] - d["z"])
        arcade = corridor == "arcade"
        length = dist * (1.12 if arcade else 1.0)
        dur = length / SPEED[mode]
        minute0 = depart.hour * 60 + depart.minute
        # sun exposure averaged over the trip
        sun = bell(minute0 + dur / 120.0) * (0.22 if arcade else 0.85)
        sun_s = dur * sun
        cov = 0.7 if arcade else 0.0
        rhl = dur * (sun * 1.0 + (1 - sun - cov) * 0.35 + cov * 0.1)
        edges = ARCADE if arcade else DIRECT
        return {
            "lambda": lam,
            "label": "x",
            "mode": mode,
            "depart": depart.isoformat(),
            "stats": {
                "distance_m": length,
                "duration_s": dur,
                "sun_exposure_s": sun_s,
                "shaded_pct": 100 * (1 - sun),
                "covered_pct": 100 * cov,
                "indoor_pct": 20.0 if arcade else 0.0,
                "rhl": rhl,
                "added_time_s": 0.0,
                "sun_saved_s": 0.0,
                "sun_saved_pct": 0.0,
                "rhl_saved_pct": 0.0,
            },
            "nodes": [o["node"], d["node"]],
            "edges": edges,
            "segments": [
                {
                    "edge": e,
                    "geometry": [[o["x"], o["z"]], [d["x"], d["z"]]],
                    "latlon": [],
                    "arrival_s": dur,
                    "t_s": dur / 3,
                    "sun": sun,
                    "cls": "covered" if arcade else "open",
                }
                for e in edges
            ],
            "corridor": corridor,
        }

    def routes(self, origin, dest, mode, depart, date_key, lams, blocked_edges=frozenset()):  # type: ignore[override]
        self.route_calls += 1
        out: dict[str, dict[str, Any]] = {}
        direct_ok = not (set(DIRECT) & blocked_edges)
        arcade_ok = not (set(ARCADE) & blocked_edges)
        if not direct_ok and not arcade_ok:
            raise BackendError("no route: both corridors are closed")
        for label, lam in lams.items():
            want_arcade = (lam >= 1.0 and arcade_ok) or not direct_ok
            out[label] = self._raw(origin, dest, mode, depart, "arcade" if want_arcade else "direct", lam)
        base = out[min(lams, key=lambda k: lams[k])]
        for r in out.values():
            st = r["stats"]
            st["added_time_s"] = st["duration_s"] - base["stats"]["duration_s"]
            st["sun_saved_s"] = base["stats"]["sun_exposure_s"] - st["sun_exposure_s"]
            st["sun_saved_pct"] = 100 * st["sun_saved_s"] / max(base["stats"]["sun_exposure_s"], 1e-9)
            st["rhl_saved_pct"] = 100 * (base["stats"]["rhl"] - st["rhl"]) / max(base["stats"]["rhl"], 1e-9)
        return {label: normalise_route(r, label, mode) for label, r in out.items()}

    def departure(self, origin, dest, mode, start, end, date_key, latest_arrival):  # type: ignore[override]
        rows, t = [], start
        while t <= end:
            r = self._raw(origin, dest, mode, t, "arcade", 1.0)["stats"]
            arrive = t + timedelta(seconds=r["duration_s"])
            if latest_arrival is None or arrive <= latest_arrival:
                rows.append(
                    {
                        "depart": t.isoformat(),
                        "duration_s": r["duration_s"],
                        "sun_exposure_s": r["sun_exposure_s"],
                        "shaded_pct": r["shaded_pct"],
                        "rhl": r["rhl"],
                    }
                )
            t += timedelta(minutes=5)
        if not rows:
            raise BackendError("no departure satisfies the latest arrival")
        best = min(
            rows,
            key=lambda r: r["rhl"] + 0.25 * (datetime.fromisoformat(r["depart"]) - start).total_seconds(),
        )
        return normalise_departure({"table": rows, "recommendation": best, "why": [{"note": "synthetic"}]})

    def sun(self, at):  # type: ignore[override]
        return {"at": at.isoformat(), "alt_deg": 70.0, "az_deg": 180.0}

    def weather(self, at):  # type: ignore[override]
        b = bell(at.hour * 60 + at.minute)
        return {"apparent_c": 30 + 14 * b, "uv": 3 + 7 * b, "source": "synthetic fixture"}

    def cool_stops(self, near, radius_m, kind):  # type: ignore[override]
        out = []
        for p in self.places.values():
            d = math.hypot(p["x"] - near["x"], p["z"] - near["z"])
            if p["id"] != near.get("id") and p["kind"] in ("mall", "hotel", "metro") and d <= radius_m:
                out.append({"id": p["id"], "name": p["name"], "kind": p["kind"], "distance_m": round(d)})
        return sorted(out, key=lambda s: s["distance_m"])

    def explain_segment(self, route, segment, date_key):  # type: ignore[override]
        return {"edge": route["edges"][segment], "street": "Synthetic Boulevard", "note": "fixture"}

    def validate_route(self, route, mode):  # type: ignore[override]
        if mode in ("cycle", "scooter"):
            return [
                f"edge {e} has stairs; forbidden for {mode}"
                for e in route.get("edges", [])
                if e in self.stairs
            ]
        return []

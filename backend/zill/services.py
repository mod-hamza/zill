"""City service layer: loads baked artifacts into numpy/CSR structures (CONTRACTS 3-4).

`get_city(city_id)` returns a cached CityContext. The baked-cities directory defaults to
`config.CITIES_DIR` and can be overridden with the env var `ZILL_CITIES_DIR` (tests do this).
"""

from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np

from zill import config
from zill.geo import to_local
from zill.routing.graph import GraphArrays, PlaceError
from zill.routing.suntable import SunTable

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class CityNotFound(KeyError):
    pass


class ShadeUnavailable(RuntimeError):
    """No exposure table for the requested date (not baked / could not be computed)."""


def cities_dir() -> Path:
    env = os.environ.get("ZILL_CITIES_DIR")
    return Path(env) if env else config.CITIES_DIR


def city_dir(city_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", city_id or ""):
        raise CityNotFound(city_id)
    d = cities_dir() / city_id
    if not d.is_dir():
        raise CityNotFound(city_id)
    return d


def list_city_ids() -> list[str]:
    root = cities_dir()
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and (p / "meta.json").exists())


def _hhmm_to_min(hhmm: np.ndarray) -> np.ndarray:
    h = np.asarray(hhmm, dtype=int)
    return (h // 100) * 60 + h % 100


@dataclass
class CityContext:
    city_id: str
    path: Path
    meta: dict[str, Any]
    graph: GraphArrays
    pois: list[dict[str, Any]]
    _tables: dict[str, SunTable] = field(default_factory=dict)
    _buildings: dict | None = None
    _lock: threading.RLock = field(default_factory=threading.RLock)

    # -- basic accessors ------------------------------------------------------------------
    @property
    def origin(self) -> dict[str, float]:
        return self.meta["origin"]

    @property
    def tz(self) -> str:
        return self.meta.get("timezone", config.TIMEZONE)

    @property
    def dates(self) -> dict[str, str]:
        return self.meta.get("dates") or config.PRESET_DATES

    @property
    def buildings(self) -> dict[str, Any]:
        if self._buildings is None:
            p = self.path / "buildings.json"
            self._buildings = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"buildings": []}
        return self._buildings

    def poi(self, poi_id: str) -> dict[str, Any] | None:
        for p in self.pois:
            if p["id"] == poi_id:
                return p
        return None

    def _poi_by_name(self, s: str) -> dict[str, Any] | None:
        s2 = s.strip().lower()
        for p in self.pois:
            if p["name"].lower() == s2:
                return p
        return None

    # -- dates / exposure -----------------------------------------------------------------
    def date_for(self, date_key: str) -> tuple[str, str]:
        """(date_id, iso) for a preset id or ISO date. date_id is the preset id if the date is one."""
        if date_key in self.dates:
            return date_key, self.dates[date_key]
        if _ISO.match(date_key or ""):
            for k, v in self.dates.items():
                if v == date_key:
                    return k, v
            return date_key, date_key
        raise ShadeUnavailable(f"unknown date key {date_key!r}")

    def date_obj(self, date_key: str) -> date:
        return date.fromisoformat(self.date_for(date_key)[1])

    def at(self, date_key: str, hhmm: str) -> datetime:
        """Aware datetime for 'HH:MM' on the date of `date_key`."""
        h, m = hhmm.split(":")[:2]
        d = self.date_obj(date_key)
        return datetime(d.year, d.month, d.day, int(h), int(m), tzinfo=ZoneInfo(self.tz))

    def exposure(self, date_key: str, compute: bool = False) -> SunTable:
        """Per-edge exposure table (SunTable) for a preset id or ISO date, cached.

        Dates that are neither baked nor already computed raise ShadeUnavailable unless
        `compute=True` (which runs the shade engine for the whole day: minutes, not milliseconds).
        """
        date_id, iso = self.date_for(date_key)
        with self._lock:
            tab = self._tables.get(date_id)
            if tab is None:
                tab = self._load_table(date_id, iso, compute)
                self._tables[date_id] = tab
            return tab

    def _load_table(self, date_id: str, iso: str, compute: bool = False) -> SunTable:
        o = self.origin
        npz = self.path / f"exposure_{date_id}.npz"
        if npz.exists():
            z = np.load(npz)
            minutes = z["minutes"] if "minutes" in z.files else _hhmm_to_min(z["hhmm"])
            expo = z["exposure"]
        else:
            expo, minutes = self._exposure_from_shade_module(date_id, iso, compute)
        if expo.shape[0] != self.graph.n_edges:
            raise ShadeUnavailable(
                f"exposure table has {expo.shape[0]} edges but graph has {self.graph.n_edges}"
            )
        return SunTable.build(date_id, iso, self.tz, np.asarray(minutes), expo, o["lat"], o["lon"])

    def _exposure_from_shade_module(self, date_id: str, iso: str, compute: bool = False):
        try:
            from zill.shade.cache import exposure_for, resolve_date
        except Exception as e:  # shade stream not available / date not baked
            raise ShadeUnavailable(f"no exposure table for {date_id} and zill.shade.cache unavailable") from e
        try:
            have = resolve_date(self.city_id, date_id).npz_path.exists()
        except Exception:
            have = False
        if not have and not compute:
            raise ShadeUnavailable(f"shade for {iso} has not been computed; POST /api/shade/compute first")
        try:
            t = exposure_for(self.city_id, iso if date_id == iso else date_id)
        except Exception as e:
            raise ShadeUnavailable(f"exposure for {date_id} could not be computed: {e}") from e
        expo = t.exposure
        minutes = getattr(t, "minutes", None)
        if minutes is None:
            minutes = _hhmm_to_min(t.hhmm)
        return np.asarray(expo), np.asarray(minutes)

    def has_exposure(self, date_key: str) -> bool:
        try:
            date_id, _ = self.date_for(date_key)
        except ShadeUnavailable:
            return False
        return (self.path / f"exposure_{date_id}.npz").exists() or date_id in self._tables

    # -- places ---------------------------------------------------------------------------
    def resolve_place(self, q: Any, mode: str = "walk") -> dict[str, Any]:
        """Resolve a place spec to {name, lat, lon, x, z, node, snap_m}.

        Accepts: poi id / exact poi name, {"lat","lon"[,"name"]}, {"poi": id}, {"node": id}, int node id.
        """
        g = self.graph
        if isinstance(q, bool):
            raise PlaceError("invalid place")
        if isinstance(q, int):
            q = {"node": q}
        if isinstance(q, str):
            p = self.poi(q) or self._poi_by_name(q)
            if p is None:
                raise PlaceError(f"unknown place {q!r}")
            q = {"lat": p["lat"], "lon": p["lon"], "name": p["name"], "poi_node": p.get("node")}
        if not isinstance(q, dict):
            raise PlaceError("invalid place")
        if q.get("poi"):
            p = self.poi(q["poi"])
            if p is None:
                raise PlaceError(f"unknown poi {q['poi']!r}")
            q = {
                "lat": p["lat"],
                "lon": p["lon"],
                "name": q.get("name") or p["name"],
                "poi_node": p.get("node"),
            }
        name = q.get("name")
        if q.get("node") is not None and "lat" not in q:
            n = int(q["node"])
            if not 0 <= n < g.n_nodes:
                raise PlaceError(f"node {n} out of range")
            x, z = float(g.x[n]), float(g.z[n])
            snap = 0.0
            lat, lon = float(g.lat[n]), float(g.lon[n])
        else:
            if "lat" not in q or "lon" not in q:
                raise PlaceError("place needs lat/lon")
            lat, lon = float(q["lat"]), float(q["lon"])
            x, z = to_local(lat, lon, self.origin)
            n, snap = g.snap(float(x), float(z), mode)
            pn = q.get("poi_node")
            if pn is not None and 0 <= int(pn) < g.n_nodes:
                mg = g.mode_graph(mode)
                if mg.ptr[int(pn) + 1] > mg.ptr[int(pn)]:  # the poi's own node is routable in this mode
                    n = int(pn)
                    snap = float(((g.x[n] - x) ** 2 + (g.z[n] - z) ** 2) ** 0.5)
        return {
            "name": name or f"{lat:.5f}, {lon:.5f}",
            "lat": lat,
            "lon": lon,
            "x": float(x),
            "z": float(z),
            "node": int(n),
            "snap_m": round(snap, 1),
        }


@lru_cache(maxsize=8)
def _load_city(city_id: str, root: str) -> CityContext:
    d = Path(root) / city_id
    if not (d / "meta.json").exists():
        raise CityNotFound(city_id)
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    graph = GraphArrays.from_json(json.loads((d / "graph.json").read_text(encoding="utf-8")))
    pois_p = d / "pois.json"
    pois = json.loads(pois_p.read_text(encoding="utf-8")).get("pois", []) if pois_p.exists() else []
    return CityContext(city_id=city_id, path=d, meta=meta, graph=graph, pois=pois)


def get_city(city_id: str) -> CityContext:
    city_dir(city_id)  # validates id + existence
    return _load_city(city_id, str(cities_dir()))


def clear_cache() -> None:
    _load_city.cache_clear()

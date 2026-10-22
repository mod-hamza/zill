"""Shade time grid, on-disk cache and loaders (PRD 7.4, CONTRACTS 3).

Preset dates live in `data/cities/<city>/shade/<date_id>/` + `exposure_<date_id>.npz`;
any other ISO date is computed on demand into `data/cache/<city>/<iso>/` (same layout).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from zill import config
from zill.shade.exposure import ExposureSampler, build_sampler
from zill.shade.heightmap import CasterGrid, GridSpec, build_caster, building_mask, load_city_inputs
from zill.shade.raymarch import compute_sun_fraction
from zill.sun.position import step_times, sun_positions

log = logging.getLogger(__name__)

CACHE_DIR = config.DATA_DIR / "cache"
_KERNEL_LOCK = threading.Lock()  # numba's default threading layer is not re-entrant across threads
_DATE_LOCKS: dict[tuple[str, str], threading.Lock] = {}
_DATE_LOCKS_GUARD = threading.Lock()

ProgressCb = Callable[[int, int, str], None]


def cities_dir() -> Path:
    return config.CITIES_DIR


# ------------------------------------------------------------------------------------------------
@dataclass
class ShadeCity:
    city_id: str
    city_dir: Path
    meta: dict[str, Any]
    core: GridSpec
    caster_spec: GridSpec
    buildings: list[dict[str, Any]]
    trees: list[dict[str, Any]]
    _caster: CasterGrid | None = None
    _mask: np.ndarray | None = None
    _sampler: ExposureSampler | None = None
    _sampler_loaded: bool = False
    _by_id: dict[int, dict[str, Any]] | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def lat(self) -> float:
        return float(self.meta["origin"]["lat"])

    @property
    def lon(self) -> float:
        return float(self.meta["origin"]["lon"])

    @property
    def tz(self) -> str:
        return str(self.meta.get("timezone", config.TIMEZONE))

    @property
    def caster(self) -> CasterGrid:
        with self._lock:
            if self._caster is None:
                t = time.perf_counter()
                self._caster = build_caster(self.caster_spec, self.buildings, self.trees)
                log.info("%s caster grid %s built in %.1fs", self.city_id, self.caster_spec.shape,
                         time.perf_counter() - t)
            return self._caster

    @property
    def mask(self) -> np.ndarray:
        with self._lock:
            if self._mask is None:
                self._mask = building_mask(self.core, self.buildings)
            return self._mask

    @property
    def sampler(self) -> ExposureSampler | None:
        mask = self.mask
        with self._lock:
            if not self._sampler_loaded:
                gp = self.city_dir / "graph.json"
                if gp.exists():
                    graph = json.loads(gp.read_text(encoding="utf-8"))
                    self._sampler = build_sampler(self.core, mask, graph["edges"])
                self._sampler_loaded = True
            return self._sampler

    def buildings_by_id(self) -> dict[int, dict[str, Any]]:
        if self._by_id is None:
            self._by_id = {int(b["id"]): b for b in self.buildings}
        return self._by_id

    def preset_dates(self) -> dict[str, str]:
        return dict(self.meta.get("dates") or config.PRESET_DATES)


@lru_cache(maxsize=8)
def get_city_shade(city_id: str) -> ShadeCity:
    city_dir = cities_dir() / city_id
    inp = load_city_inputs(city_dir)
    meta = inp["meta"]
    core = GridSpec.from_dict(meta["core_grid"])
    caster = GridSpec.from_dict(meta["caster_grid"])
    return ShadeCity(city_id, city_dir, meta, core, caster, inp["buildings"], inp["trees"])


# ------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class DateTarget:
    city_id: str
    date_id: str  # preset id or ISO date
    iso: str
    out_dir: Path  # where step PNGs + index.json go
    npz_path: Path
    preset: bool


def resolve_date(city_id: str, date_key: str) -> DateTarget:
    sc = get_city_shade(city_id)
    presets = sc.preset_dates()
    if date_key in presets:
        did, iso = date_key, presets[date_key]
    else:
        iso = date.fromisoformat(date_key).isoformat()
        did = next((k for k, v in presets.items() if v == iso), iso)
    if did in presets:
        return DateTarget(city_id, did, iso, sc.city_dir / "shade" / did,
                          sc.city_dir / f"exposure_{did}.npz", True)
    d = CACHE_DIR / city_id / iso
    return DateTarget(city_id, iso, iso, d, d / f"exposure_{iso}.npz", False)


def hhmm_of(ts: datetime) -> str:
    return f"{ts.hour:02d}{ts.minute:02d}"


def plan_steps(sc: ShadeCity, iso: str) -> list[dict[str, Any]]:
    times = step_times(date.fromisoformat(iso), sc.lat, sc.lon, sc.tz)
    pos = sun_positions(times, sc.lat, sc.lon, sc.tz)
    out = []
    for ts, p in zip(times, pos, strict=True):
        hh = hhmm_of(ts)
        out.append({"hhmm": hh, "ts": ts.isoformat(), "alt": round(p.alt_deg, 3), "az": round(p.az_deg, 3),
                    "night": bool(p.alt_deg <= config.SUN_MIN_ALT_DEG), "file": f"step_{hh}.png"})
    return out


def compute_step(sc: ShadeCity, alt: float, az: float) -> np.ndarray:
    caster, mask = sc.caster, sc.mask
    with _KERNEL_LOCK:
        return compute_sun_fraction(caster, sc.core, alt, az, mask)


def write_png(path: Path, arr: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.png")
    Image.fromarray(np.ascontiguousarray(arr, dtype=np.uint8)).save(tmp, format="PNG", optimize=True)
    tmp.replace(path)


def read_png(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        return np.asarray(im.convert("L"), dtype=np.uint8)


def _date_lock(city_id: str, iso: str) -> threading.Lock:
    with _DATE_LOCKS_GUARD:
        return _DATE_LOCKS.setdefault((city_id, iso), threading.Lock())


def compute_date(city_id: str, date_key: str, progress_cb: ProgressCb | None = None,
                 first_hhmm: str | None = None, force: bool = False,
                 exposure_only: bool = False) -> dict[str, Any]:
    """Compute (or reuse) every step of a date + the exposure table. Requested step first.

    Thread-pool friendly: one lock per (city, date); kernels serialised by a global lock.
    `exposure_only=True` re-reads existing step PNGs and only rebuilds the exposure npz (cheap; use it
    after graph.json changes). Missing PNGs are still computed.
    Returns the index.json dict (with an extra "timing" block).
    """
    tgt = resolve_date(city_id, date_key)
    sc = get_city_shade(city_id)
    with _date_lock(city_id, tgt.iso):
        idx_path = tgt.out_dir / "index.json"
        if idx_path.exists() and tgt.npz_path.exists() and not force and not exposure_only:
            return json.loads(idx_path.read_text(encoding="utf-8"))
        steps = plan_steps(sc, tgt.iso)
        order = list(range(len(steps)))
        if first_hhmm is not None:
            first = min(order, key=lambda i: abs(_minutes(steps[i]["hhmm"]) - _minutes(first_hhmm)))
            order.remove(first)
            order.insert(0, first)
        sampler = sc.sampler
        expo = np.zeros((sampler.n_edges if sampler else 0, len(steps)), np.float32)
        t_steps: list[float] = []
        t_png: list[float] = []
        t0 = time.perf_counter()
        for n, i in enumerate(order):
            st = steps[i]
            png = tgt.out_dir / st["file"]
            if png.exists() and (exposure_only or not force):
                sf = read_png(png)
            else:
                ts = time.perf_counter()
                sf = compute_step(sc, st["alt"], st["az"])
                if not st["night"]:
                    t_steps.append(time.perf_counter() - ts)
                ts = time.perf_counter()
                write_png(png, sf)
                t_png.append(time.perf_counter() - ts)
            if sampler is not None:
                expo[:, i] = sampler.exposure(sf)
            if progress_cb is not None:
                progress_cb(n + 1, len(steps), st["hhmm"])
        index = {"date": tgt.iso, "date_id": tgt.date_id, "steps": steps}
        tgt.out_dir.mkdir(parents=True, exist_ok=True)
        idx_path.write_text(json.dumps(index, indent=1), encoding="utf-8")
        if sampler is not None:
            hh = np.array([int(s["hhmm"]) for s in steps], np.int16)
            mins = np.array([_minutes(s["hhmm"]) for s in steps], np.int16)
            tmp = tgt.npz_path.with_suffix(".tmp.npz")
            np.savez_compressed(tmp, exposure=expo.astype(np.float16), hhmm=hh, minutes=mins)
            tmp.replace(tgt.npz_path)
            _exposure_cached.cache_clear()
        index["timing"] = {
            "total_s": round(time.perf_counter() - t0, 2),
            "computed_steps": len(t_steps),
            "step_mean_s": round(float(np.mean(t_steps)), 3) if t_steps else None,
            "step_max_s": round(float(np.max(t_steps)), 3) if t_steps else None,
            "png_write_mean_s": round(float(np.mean(t_png)), 3) if t_png else None,
        }
        if sampler is not None:
            index["exposure_stats"] = sampler.stats
        return index


def _minutes(hhmm: str | int) -> int:
    v = int(hhmm)
    return (v // 100) * 60 + v % 100


def get_shade_step(city_id: str, date_key: str, hhmm: str | int) -> np.ndarray:
    """uint8 sun-fraction raster for one step (nearest 10-min step; computed + cached if missing)."""
    tgt = resolve_date(city_id, date_key)
    hh = f"{int(hhmm):04d}"
    png = tgt.out_dir / f"step_{hh}.png"
    if png.exists():
        return read_png(png)
    sc = get_city_shade(city_id)
    steps = plan_steps(sc, tgt.iso)
    st = min(steps, key=lambda s: abs(_minutes(s["hhmm"]) - _minutes(hh)))
    png = tgt.out_dir / st["file"]
    if png.exists():
        return read_png(png)
    sf = compute_step(sc, st["alt"], st["az"])
    write_png(png, sf)
    return sf


@dataclass(frozen=True)
class ExposureTable:
    date_key: str
    iso: str
    exposure: np.ndarray  # float32 [n_edges, n_steps], 0..1
    hhmm: np.ndarray  # int16 [n_steps]
    minutes: np.ndarray  # int16 [n_steps], minutes since local midnight

    @property
    def n_edges(self) -> int:
        return int(self.exposure.shape[0])

    def at(self, minute_of_day: float) -> np.ndarray:
        """float32 [n_edges]: exposure linearly interpolated between the two nearest steps."""
        m = self.minutes.astype(np.float64)
        if minute_of_day <= m[0]:
            return self.exposure[:, 0]
        if minute_of_day >= m[-1]:
            return self.exposure[:, -1]
        j = int(np.searchsorted(m, minute_of_day, side="right"))
        f = (minute_of_day - m[j - 1]) / (m[j] - m[j - 1])
        return (self.exposure[:, j - 1] * (1 - f) + self.exposure[:, j] * f).astype(np.float32)

    def edge_at(self, edge: int, minute_of_day: float) -> float:
        return float(np.interp(minute_of_day, self.minutes.astype(np.float64), self.exposure[edge]))


def exposure_for(city_id: str, date_key: str) -> ExposureTable:
    """Memoised exposure table; computes the date on demand if it is not on disk yet.

    `date_key` is a preset id or an ISO date (the ISO date of a preset maps to the preset).
    """
    return _exposure_cached(city_id, resolve_date(city_id, date_key).date_id)


@lru_cache(maxsize=16)
def _exposure_cached(city_id: str, date_key: str) -> ExposureTable:
    tgt = resolve_date(city_id, date_key)
    if not tgt.npz_path.exists():
        compute_date(city_id, date_key)
    with np.load(tgt.npz_path) as z:
        return ExposureTable(tgt.date_id, tgt.iso, z["exposure"].astype(np.float32), z["hhmm"].copy(),
                             z["minutes"].copy())


exposure_for.cache_clear = _exposure_cached.cache_clear  # type: ignore[attr-defined]

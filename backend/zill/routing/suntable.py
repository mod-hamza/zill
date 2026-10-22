"""Per-edge sun exposure table + solar altitude/uv per step, with arrival-time interpolation.

Exposure is looked up at the clock time the traveller ARRIVES at an edge (PRD 7.5), linearly
interpolated between the two nearest 10-minute steps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np

from zill.routing.heat import uv_factor


@dataclass
class SunTable:
    date_id: str
    iso: str
    tz: str
    minutes: np.ndarray  # float64 [n_steps], uniform, minutes since local midnight
    exposure: np.ndarray  # float32 [n_edges, n_steps]
    alt: np.ndarray  # float64 [n_steps] solar altitude deg
    uv: np.ndarray  # float64 [n_steps] uv factor
    m0: float = 0.0
    step: float = 10.0
    n: int = 0
    flat: memoryview = field(default=None, repr=False)  # type: ignore[assignment]
    uv_list: list[float] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        self.n = int(self.minutes.shape[0])
        self.m0 = float(self.minutes[0])
        self.step = float(self.minutes[1] - self.minutes[0]) if self.n > 1 else 10.0
        self.exposure = np.ascontiguousarray(self.exposure, dtype=np.float32)
        self.flat = memoryview(self.exposure.reshape(-1))
        self.uv_list = self.uv.tolist()

    @property
    def n_edges(self) -> int:
        return int(self.exposure.shape[0])

    def day0(self) -> datetime:
        d = date.fromisoformat(self.iso)
        return datetime(d.year, d.month, d.day, tzinfo=ZoneInfo(self.tz))

    def minute_of(self, ts: datetime) -> float:
        """Clock minutes since local midnight (time-of-day of `ts` in the city timezone)."""
        t = ts.astimezone(ZoneInfo(self.tz)) if ts.tzinfo else ts
        return t.hour * 60 + t.minute + t.second / 60.0 + t.microsecond / 6e7

    def to_dt(self, minute: float) -> datetime:
        return self.day0() + timedelta(minutes=float(minute))

    def locate(self, minute: float) -> tuple[int, float]:
        """(k, frac): value = a[k] + (a[k+1]-a[k])*frac, clamped to the table range."""
        pos = (minute - self.m0) / self.step
        if pos <= 0.0:
            return 0, 0.0
        k = int(pos)
        if k >= self.n - 1:
            return max(self.n - 2, 0), 1.0
        return k, pos - k

    def sun(self, edge: int, minute: float) -> float:
        k, fr = self.locate(minute)
        n = self.n
        if n < 2:
            return float(self.flat[edge * n])
        i = edge * n + k
        a = self.flat[i]
        return a + (self.flat[i + 1] - a) * fr

    def uv_at(self, minute: float) -> float:
        k, fr = self.locate(minute)
        if self.n < 2:
            return self.uv_list[0]
        a = self.uv_list[k]
        return a + (self.uv_list[k + 1] - a) * fr

    def alt_at(self, minute: float) -> float:
        return float(np.interp(minute, self.minutes, self.alt))

    @classmethod
    def build(
        cls,
        date_id: str,
        iso: str,
        tz: str,
        minutes: np.ndarray,
        exposure: np.ndarray,
        lat: float,
        lon: float,
    ) -> SunTable:
        minutes = np.asarray(minutes, dtype=np.float64)
        exposure = np.asarray(exposure, dtype=np.float32)
        if minutes.shape[0] > 2:
            diffs = np.diff(minutes)
            if not np.allclose(diffs, diffs[0]):  # resample onto a uniform grid
                step = float(np.min(diffs))
                grid = np.arange(minutes[0], minutes[-1] + 1e-6, step)
                exposure = np.stack([np.interp(grid, minutes, row) for row in exposure]).astype(np.float32)
                minutes = grid
        alt = _alts(iso, tz, minutes, lat, lon)
        return cls(
            date_id=date_id,
            iso=iso,
            tz=tz,
            minutes=minutes,
            exposure=exposure,
            alt=alt,
            uv=np.asarray(uv_factor(alt), dtype=float),
        )


def _alts(iso: str, tz: str, minutes: np.ndarray, lat: float, lon: float) -> np.ndarray:
    from zill.sun.position import sun_positions

    d = date.fromisoformat(iso)
    day0 = datetime(d.year, d.month, d.day, tzinfo=ZoneInfo(tz))
    times = [day0 + timedelta(minutes=float(m)) for m in minutes]
    return np.array([p.alt_deg for p in sun_positions(times, lat, lon, tz)], dtype=float)

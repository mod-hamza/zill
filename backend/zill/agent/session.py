"""Agent session state: persona, city, simulated clock, autonomy, plans, result store, history."""

from __future__ import annotations

import itertools
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from zill import config

from .backend import ToolBackend
from .tokens import ResultStore

AUTONOMY_LABELS = {1: "advisor", 2: "planner", 3: "autopilot"}


class SimClock:
    """Simulated clock. Default x60 (1 real second = 1 sim minute); jumpable; injectable real time."""

    def __init__(
        self, start: datetime, rate: float = 60.0, real: Callable[[], float] = time.monotonic
    ) -> None:
        self._base = start
        self._real = real
        self._t0 = real()
        self.rate = rate

    def now(self) -> datetime:
        return self._base + timedelta(seconds=(self._real() - self._t0) * self.rate)

    def jump(self, to: datetime) -> None:
        self._base, self._t0 = to, self._real()

    def advance(self, minutes: float) -> datetime:
        self.jump(self.now() + timedelta(minutes=minutes))
        return self.now()


def parse_clock(value: Any, date_iso: str, tz: str) -> datetime:
    """'HH:MM' | ISO string | datetime -> aware datetime in the city timezone."""
    z = ZoneInfo(tz)
    if isinstance(value, datetime):
        return value.astimezone(z) if value.tzinfo else value.replace(tzinfo=z)
    s = str(value).strip()
    if len(s) <= 5 and ":" in s:
        h, m = s.split(":")
        d = datetime.fromisoformat(date_iso)
        return d.replace(hour=int(h), minute=int(m), second=0, microsecond=0, tzinfo=z)
    d = datetime.fromisoformat(s)
    return d.astimezone(z) if d.tzinfo else d.replace(tzinfo=z)


@dataclass
class Session:
    persona: str
    backend: ToolBackend
    date_key: str = "summer"
    city: str = config.DEFAULT_CITY
    autonomy: int = 2
    clock: SimClock | None = None
    id: str = field(default_factory=lambda: "s_" + uuid.uuid4().hex[:10])
    store: ResultStore = field(default_factory=ResultStore)
    plans: dict[str, dict[str, Any]] = field(default_factory=dict)
    draft_plan_id: str | None = None
    active_plan_id: str | None = None
    pending: dict[str, Any] | None = None
    history: list[dict[str, Any]] = field(default_factory=list)
    conditions: list[dict[str, Any]] = field(default_factory=list)
    autonomy_log: list[dict[str, Any]] = field(default_factory=list)
    undo: dict[str, dict[str, Any]] = field(default_factory=dict)
    user_text: str = ""
    calls_this_turn: int = 0
    replay_scenario: str | None = None
    _plan_seq: itertools.count = field(default_factory=lambda: itertools.count(1))
    _undo_seq: itertools.count = field(default_factory=lambda: itertools.count(1))

    def __post_init__(self) -> None:
        self.autonomy = max(1, min(3, int(self.autonomy)))
        self.store = ResultStore(self.backend.tz)
        if self.clock is None:
            day = self.backend.date_obj(self.date_key)
            self.clock = SimClock(day.replace(hour=13, minute=0), rate=60.0)

    # -- helpers ----------------------------------------------------------------------------
    def date_iso(self) -> str:
        return self.backend.date_obj(self.date_key).date().isoformat()

    def parse_time(self, value: Any) -> datetime:
        return parse_clock(value, self.date_iso(), self.backend.tz)

    def new_plan_id(self) -> str:
        return f"plan_{next(self._plan_seq)}"

    def new_undo_token(self) -> str:
        return f"undo_{next(self._undo_seq)}"

    @property
    def active_plan(self) -> dict[str, Any] | None:
        return self.plans.get(self.active_plan_id) if self.active_plan_id else None

    def draft_plan(self) -> dict[str, Any] | None:
        return self.plans.get(self.draft_plan_id) if self.draft_plan_id else None

    def public(self) -> dict[str, Any]:
        return {
            "session_id": self.id,
            "persona": self.persona,
            "city": self.city,
            "date_key": self.date_key,
            "autonomy_level": self.autonomy,
            "autonomy": AUTONOMY_LABELS[self.autonomy],
            "sim_time": self.clock.now().isoformat() if self.clock else None,
            "active_plan_id": self.active_plan_id,
        }


def plan_active_route(plan: dict[str, Any]) -> dict[str, Any] | None:
    rec = plan.get("recommendation")
    routes = plan.get("routes") or {}
    if rec and rec in routes:
        return routes[rec]
    if routes:
        return routes.get("balanced") or next(iter(routes.values()))
    return None


def plan_summary(plan: dict[str, Any]) -> dict[str, Any]:
    """Flat, token-friendly summary of a plan's recommended route (stored under `plan`)."""
    r = plan_active_route(plan) or {}
    return {
        "id": plan["plan_id"],
        "kind": plan.get("kind", "journey"),
        "mode": plan.get("mode"),
        "recommendation": plan.get("recommendation"),
        "depart": r.get("depart") or plan.get("depart"),
        "arrive": r.get("arrive"),
        "duration_s": r.get("duration_s"),
        "distance_m": r.get("distance_m"),
        "sun_exposure_s": r.get("sun_exposure_s"),
        "shaded_pct": r.get("shaded_pct"),
        "rhl": r.get("rhl"),
        "status": plan.get("status", "draft"),
    }

# ruff: noqa: E501
"""Monitor (PRD 11.2.3, 11.5): proactive re-evaluation of the active plan on the simulated clock.

Conditions (delay, closure, heat_alert) are injected via `inject`/`simulate`; each `tick` re-runs the
real routing for the committed plan and applies the autonomy policy:
  L1 advisor  : suggest only, never change the plan
  L2 planner  : every replan needs approval
  L3 autopilot: auto-apply when |delta arrival| <= 10 min and RHL not worse than +10%, else ask.
Every autonomous action is logged with a reason and an `undo` token.

Delta arrival definition (documented in DECISIONS.md): the replan's arrival is compared with the
*disrupted baseline* (committed arrival plus the delay for a delay; the committed arrival for a
closure or heat alert). For a fixed path the duration does not depend on clock time (constant speed),
so the baseline arrival after a delay is exactly committed arrival + delay.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from zill import config

from .backend import BackendError
from .narration import replan_message
from .session import plan_active_route, plan_summary

if TYPE_CHECKING:  # pragma: no cover
    from .orchestrator import Agent

KINDS = ("delay", "closure", "heat_alert", "sun_clock_jump", "tick")


class Monitor:
    def __init__(self, agent: Agent) -> None:
        self.agent = agent

    @property
    def s(self):  # noqa: ANN201
        return self.agent.s

    # -- injection -------------------------------------------------------------------------
    def inject(self, kind: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        if kind not in KINDS:
            raise ValueError(f"unknown event type '{kind}'")
        if kind == "sun_clock_jump":
            to = params.get("to")
            if to:
                self.s.clock.jump(self.s.parse_time(to))
            else:
                self.s.clock.advance(float(params.get("minutes", 30)))
            return {"type": kind, "handled": True}
        if kind == "tick":
            self.s.clock.advance(float(params.get("minutes", 1)))
            return {"type": kind, "handled": True}
        cond = {"type": kind, **params, "handled": False, "at": self.s.clock.now().isoformat()}
        if kind == "delay":
            cond["minutes"] = float(params.get("minutes", 20))
        self.s.conditions.append(cond)
        return cond

    def simulate(self, kind: str, params: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
        try:
            self.inject(kind, params)
        except ValueError as exc:
            yield self.agent.emit("error", {"message": str(exc), "recoverable": True})
            return
        yield from self.tick()

    # -- tick ------------------------------------------------------------------------------
    def tick(self) -> Iterator[dict[str, Any]]:
        s, emit = self.s, self.agent.emit
        now = s.clock.now()
        plan = s.active_plan
        if plan is None:
            yield emit(
                "monitor_tick",
                {"sim_time": now.isoformat(), "status": "idle", "note": "No committed plan to watch."},
            )
            return
        self._poll_weather(plan)
        pending = [c for c in s.conditions if not c["handled"]]
        if not pending:
            yield emit("monitor_tick", {"sim_time": now.isoformat(), "status": "on_track"})
            return
        yield emit(
            "monitor_tick",
            {"sim_time": now.isoformat(), "status": "deviation", "conditions": [c["type"] for c in pending]},
        )
        for cond in pending:
            cond["handled"] = True
            yield from self._handle(s.active_plan or plan, cond)

    def _poll_weather(self, plan: dict[str, Any]) -> None:
        """Heat alert from the weather module (apparent temp >= 40 C or UV >= 8) at the plan's time."""
        s = self.s
        if any(c["type"] == "heat_alert" for c in s.conditions) or plan.get("heat_checked"):
            return
        plan["heat_checked"] = True
        if s.store.has("weather"):  # the planner already looked at the heat context for this plan
            return
        r = plan_active_route(plan)
        if not r:
            return
        try:
            w = s.backend.weather(datetime.fromisoformat(r["depart"]))
        except BackendError:
            return
        if w.get("heat_alert") or (w.get("apparent_c") or 0) >= 40 or (w.get("uv") or 0) >= 8:
            s.conditions.append(
                {"type": "heat_alert", "source": "weather", "handled": False, "at": s.clock.now().isoformat()}
            )

    # -- replanning ------------------------------------------------------------------------
    def _handle(self, plan: dict[str, Any], cond: dict[str, Any]) -> Iterator[dict[str, Any]]:
        s, emit = self.s, self.agent.emit
        kind = cond["type"]
        old = plan_active_route(plan)
        if old is None or plan.get("kind") == "day":
            yield emit(
                "monitor_tick",
                {
                    "sim_time": s.clock.now().isoformat(),
                    "status": "unsupported",
                    "note": "Re-planning of multi-stop day plans is not simulated.",
                },
            )
            return
        rec = plan.get("recommendation") or "balanced"
        o, d, mode = plan["origin"], plan["dest"], plan["mode"]
        depart = datetime.fromisoformat(old["depart"])
        old_arrive = datetime.fromisoformat(old["arrive"])
        blocked = frozenset(int(c["edge"]) for c in s.conditions if c["type"] == "closure" and "edge" in c)
        delay_s = 0.0
        if kind == "delay":
            delay_s = float(cond["minutes"]) * 60.0
            depart = depart + timedelta(seconds=delay_s)
            baseline_arrive = old_arrive + timedelta(seconds=delay_s)
            reason = "Departure delayed; shade moved while you waited."
        elif kind == "closure":
            if "edge" in cond and int(cond["edge"]) not in set(old.get("edges", [])):
                yield emit(
                    "monitor_tick",
                    {
                        "sim_time": s.clock.now().isoformat(),
                        "status": "on_track",
                        "note": "A closure was reported but it is not on your route.",
                    },
                )
                return
            baseline_arrive = old_arrive
            reason = "A closure blocks your route."
        else:  # heat_alert
            baseline_arrive = old_arrive
            if rec == "coolest" and not cond.get("force"):
                text = (
                    "Heat alert noted: your plan already uses the coolest option. Carry water and take shade "
                    "breaks; I will keep watching."
                )
                yield emit(
                    "monitor_tick",
                    {
                        "sim_time": s.clock.now().isoformat(),
                        "status": "on_track",
                        "note": "Heat alert: plan already uses the coolest route.",
                    },
                )
                yield emit("message", {"text": text, "resolved": [], "template": text, "source": "monitor"})
                return
            rec = "coolest"
            reason = "Heat alert at your travel time; prefer more shade and cover."
        try:
            routes = s.backend.routes(o, d, mode, depart, plan["date_key"], dict(config.LAMBDAS), blocked)
        except BackendError as exc:
            s.store.set(
                "replan",
                {"kind": kind, "reason": reason, "blocked": True, "error": str(exc), "delay_s": delay_s},
            )
            yield emit(
                "replan",
                {
                    "reason": reason,
                    "kind": kind,
                    "diff": {"blocked": True},
                    "auto": False,
                    "new_plan_id": None,
                },
            )
            tpl = replan_message(s.store, False, kind)
            res = s.store.resolve(tpl)
            yield emit(
                "message", {"text": res.text, "resolved": res.resolved, "template": tpl, "source": "monitor"}
            )
            return
        new = routes.get(rec) or next(iter(routes.values()))
        new_arrive = datetime.fromisoformat(new["arrive"])
        delta_s = (new_arrive - baseline_arrive).total_seconds()
        d_committed_s = (new_arrive - old_arrive).total_seconds()
        old_rhl, new_rhl = float(old.get("rhl") or 0.0), float(new.get("rhl") or 0.0)
        d_rhl_pct = 100.0 * (new_rhl - old_rhl) / old_rhl if old_rhl > 0 else 0.0
        small = (
            abs(delta_s) <= config.AUTO_APPLY_MAX_DELTA_ARRIVAL_MIN * 60.0
            and d_rhl_pct <= config.AUTO_APPLY_MAX_RHL_INCREASE_PCT
        )
        auto = s.autonomy == 3 and small
        route_changed = new.get("edges") != old.get("edges")
        diff = {
            "old": {
                "depart": old["depart"],
                "arrive": old["arrive"],
                "rhl": old_rhl,
                "duration_s": old["duration_s"],
                "sun_exposure_s": old.get("sun_exposure_s"),
            },
            "new": {
                "depart": new["depart"],
                "arrive": new["arrive"],
                "rhl": new_rhl,
                "duration_s": new["duration_s"],
                "sun_exposure_s": new.get("sun_exposure_s"),
            },
            "delay_s": delay_s,
            "delta_arrival_s": delta_s,
            "delta_arrival_vs_committed_s": d_committed_s,
            "delta_rhl_pct": d_rhl_pct,
            "route_changed": route_changed,
            "blocked": False,
            "baseline_rhl_basis": "committed plan as planned",
        }
        s.store.set("replan", {"kind": kind, "reason": reason, "auto": auto, **diff})
        new_plan = {
            **plan,
            "plan_id": s.new_plan_id(),
            "routes": routes,
            "recommendation": rec,
            "depart": new["depart"],
            "status": "draft",
            "parent": plan["plan_id"],
            "heat_checked": True,
        }
        new_plan.pop("policy_acknowledged", None)
        s.plans[new_plan["plan_id"]] = new_plan
        yield emit(
            "replan",
            {
                "reason": reason,
                "kind": kind,
                "diff": diff,
                "auto": auto,
                "new_plan_id": new_plan["plan_id"],
                "routes": [routes[k] for k in ("fastest", "balanced", "coolest") if k in routes],
            },
        )
        msg_auto = auto
        if auto:
            token = s.new_undo_token()
            s.undo[token] = {"prev_plan_id": plan["plan_id"], "new_plan_id": new_plan["plan_id"]}
            entry = {
                "at": s.clock.now().isoformat(),
                "action": "auto_apply",
                "reason": reason,
                "plan_id": new_plan["plan_id"],
                "undo_token": token,
                "delta_arrival_s": delta_s,
                "delta_rhl_pct": d_rhl_pct,
            }
            s.autonomy_log.append(entry)
            yield from self.agent.commit(new_plan, auto=True, reason=reason, undo_token=token)
            yield emit(
                "monitor_tick",
                {
                    "sim_time": s.clock.now().isoformat(),
                    "status": "replanned",
                    "note": "Auto-applied under Autopilot; undo available.",
                    "undo_token": token,
                },
            )
        elif s.autonomy >= 2:
            s.pending = {"plan_id": new_plan["plan_id"], "kind": "replan", "reason": reason}
            yield emit(
                "approval_request",
                {
                    "plan_id": new_plan["plan_id"],
                    "risk": "medium" if not small else "low",
                    "options": [
                        {"id": "approve", "label": "Apply new plan"},
                        {"id": "reject", "label": "Keep current plan"},
                    ],
                    "reason": (
                        "Autopilot only applies changes up to 10 minutes of arrival shift and 10% more heat load."
                        if s.autonomy == 3
                        else "Autonomy L2 asks before changing a committed plan."
                    ),
                },
            )
        text = replan_message(s.store, msg_auto, kind)
        if s.autonomy == 1:
            text = (
                text.split(" Applied automatically")[0].split(" The change is larger")[0]
                + " Advisor mode: I only suggest, I have changed nothing."
            )
        res = s.store.resolve(text)
        yield emit(
            "message", {"text": res.text, "resolved": res.resolved, "template": text, "source": "monitor"}
        )

    # -- undo ------------------------------------------------------------------------------
    def undo(self, token: str) -> Iterator[dict[str, Any]]:
        s, emit = self.s, self.agent.emit
        rec = s.undo.pop(token, None)
        if rec is None:
            yield emit("error", {"message": "That undo token is not available.", "recoverable": True})
            return
        prev = s.plans[rec["prev_plan_id"]]
        s.autonomy_log.append(
            {
                "at": s.clock.now().isoformat(),
                "action": "undo",
                "undo_token": token,
                "plan_id": prev["plan_id"],
                "reason": "Reverted by the user.",
            }
        )
        prev["status"] = "committed"
        s.active_plan_id = prev["plan_id"]
        s.store.set("plan", plan_summary(prev))
        yield emit(
            "plan_committed",
            {
                "plan_id": prev["plan_id"],
                "auto": False,
                "undo": True,
                "reason": "Autonomous change reverted by the user.",
                "summary": plan_summary(prev),
                "autonomy_level": s.autonomy,
            },
        )

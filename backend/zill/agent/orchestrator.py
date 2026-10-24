# ruff: noqa: E501
"""Agent orchestrator: Planner tool loop -> Verifier -> Narrator -> events (PRD 11.2-11.5).

`Agent.run_turn(user_text)` is a generator of SSE-ready events `{id, ts, type, payload}`.
Roles use separate system prompts (prompts.py). Numbers in user-facing text are tokens resolved
from the session ResultStore; text with unresolved tokens or bare numbers is never sent.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any

from zill import config

from .llm import LLMError, assistant_message
from .monitor import Monitor
from .narration import template_message
from .personas import get_persona
from .prompts import narrator_prompt, planner_prompt
from .session import AUTONOMY_LABELS, Session, plan_active_route, plan_summary
from .tokens import check_text, find_violations, redact_bare_numbers
from .tools import execute, model_view, planner_specs
from .verifier import Draft, VerifyResult, merge, parse_draft, verify_deterministic, verify_llm

MAX_PLANNER_STEPS = 20


def _utc_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class Emitter:
    def __init__(self, now: Callable[[], str] = _utc_iso) -> None:
        self._n = 0
        self._now = now

    def __call__(self, type_: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._n += 1
        return {"id": f"evt_{self._n:04d}", "ts": self._now(), "type": type_, "payload": payload}


class Agent:
    def __init__(self, session: Session, llm: Any, now: Callable[[], str] = _utc_iso) -> None:
        self.s = session
        self.llm = llm
        self.emit = Emitter(now)
        self.started = False
        self.monitor = Monitor(self)

    # ------------------------------------------------------------------------------------------
    def _context(self) -> str:
        s = self.s
        ap = s.active_plan
        return (
            f"City: {s.city}. Date preset: {s.date_key} ({s.date_iso()}). Simulated clock: "
            f"{s.clock.now().strftime('%H:%M')} Gulf time. Autonomy: L{s.autonomy} {AUTONOMY_LABELS[s.autonomy]}. "
            f"Active plan: {json.dumps(plan_summary(ap), default=str) if ap else 'none'}."
        )

    def session_started(self) -> dict[str, Any]:
        self.started = True
        return self.emit(
            "session_started", {**self.s.public(), "llm_scripted": bool(getattr(self.llm, "scripted", False))}
        )

    # ------------------------------------------------------------------------------------------
    def run_turn(self, user_text: str) -> Iterator[dict[str, Any]]:
        s = self.s
        s.user_text = user_text
        s.calls_this_turn = 0
        s.pending = None
        if not self.started:
            yield self.session_started()
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": planner_prompt(s.persona, self._context())},
            *s.history,
            {"role": "user", "content": user_text},
        ]
        fix_rounds = 0
        verdict = VerifyResult()
        draft: Draft | None = None
        while True:
            try:
                draft = yield from self._planner_loop(messages)
            except LLMError as exc:
                yield self.emit(
                    "error",
                    {
                        "message": "The language model is unreachable right now.",
                        "detail": str(exc),
                        "recoverable": True,
                    },
                )
                return
            if draft is None:
                yield self.emit(
                    "error", {"message": "The planner did not produce a proposal.", "recoverable": True}
                )
                return
            verdict = verify_deterministic(s, draft, user_text)
            if not getattr(self.llm, "scripted", False) and verdict.passed:
                try:
                    verdict = merge(verdict, verify_llm(self.llm, s, draft, user_text))
                except LLMError:
                    verdict.layers.append("llm_unavailable")
            yield self.emit("verifier", verdict.payload())
            if verdict.passed:
                break
            if fix_rounds >= config.MAX_FIX_ROUNDS:
                plan = s.draft_plan()
                if plan is not None and all("policy" in d or "conflicts with" in d for d in verdict.defects):
                    plan["policy_acknowledged"] = True  # flagged explicitly to the user, not hidden
                    break
                yield self.emit(
                    "error",
                    {
                        "message": "I could not produce a plan that passes verification.",
                        "defects": verdict.defects,
                        "recoverable": True,
                    },
                )
                return
            fix_rounds += 1
            yield self.emit(
                "thought",
                {"text": f"Verifier found {len(verdict.defects)} defect(s); revising (round {fix_rounds})."},
            )
            messages.append(
                {
                    "role": "assistant",
                    "content": json.dumps(
                        {"plan_id": draft.plan_id, "recommendation": draft.recommendation, "text": draft.text}
                    ),
                }
            )
            messages.append(
                {
                    "role": "user",
                    "content": "VERIFIER DEFECTS (fix and resubmit the JSON, using tools if needed):\n- "
                    + "\n- ".join(verdict.defects),
                }
            )

        plan = s.plans.get(draft.plan_id or s.draft_plan_id or "")
        rec = draft.recommendation or (plan or {}).get("recommendation") or "coolest"
        if plan is not None:
            plan["recommendation"] = (
                rec if rec in plan["routes"] or plan.get("kind") == "day" else plan.get("recommendation")
            )
            s.draft_plan_id = plan["plan_id"]
            s.store.set("plan", plan_summary(plan))
        yield from self._proposal_events(plan, draft, rec)
        text, resolved, template, source = self._narrate(draft, plan, rec)
        s.history.append({"role": "user", "content": user_text})
        s.history.append({"role": "assistant", "content": text})
        s.history = s.history[-12:]
        yield self.emit(
            "message", {"text": text, "resolved": resolved, "template": template, "source": source}
        )

    # ------------------------------------------------------------------------------------------
    def _planner_loop(self, messages: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        """Generator: yields tool events, returns the Draft (via StopIteration value)."""
        s = self.s
        for _ in range(MAX_PLANNER_STEPS):
            res = self.llm.chat(messages, tools=planner_specs())
            messages.append(assistant_message(res))
            if not res.tool_calls:
                return parse_draft(res.content)
            note = (res.content or "").strip()
            if note and len(note) <= 240 and not find_violations(note, s.user_text):
                yield self.emit("thought", {"text": note})
            for tc in res.tool_calls:
                yield self.emit("tool_call", {"name": tc.name, "args": tc.arguments})
                if tc.arguments_error:
                    result, ms = (
                        {"ok": False, "data": {"error": tc.arguments_error}, "summary": tc.arguments_error},
                        0,
                    )
                else:
                    result, ms = execute(s, tc.name, tc.arguments)
                payload = {"name": tc.name, "ok": result["ok"], "summary": result["summary"], "duration_ms": ms}
                if tc.name == "compare_routes" and result["ok"]:  # computed stats, for audit against hero.json
                    payload["data"] = {
                        "plan_id": result["data"]["plan_id"],
                        "routes": {
                            k: {"depart": v.get("depart"), "stats": v["stats"]}
                            for k, v in result["data"]["routes"].items()
                        },
                    }
                yield self.emit("tool_result", payload)
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": model_view(s, result)})
        return None

    def _proposal_events(
        self, plan: dict[str, Any] | None, draft: Draft, rec: str
    ) -> Iterator[dict[str, Any]]:
        s = self.s
        if plan is None:
            return
        routes = [r for r in (plan["routes"].get(k) for k in ("fastest", "balanced", "coolest", "sunniest")) if r]
        tokens = {t["token"]: t["value"] for t in s.store.resolve(draft.text).resolved}
        weather = s.store.get("weather") or {}
        high = bool(plan.get("policy_acknowledged")) or bool(weather.get("heat_alert"))
        yield self.emit(
            "proposal",
            {
                "plan_id": plan["plan_id"],
                "kind": plan.get("kind", "journey"),
                "mode": plan["mode"],
                "routes": routes if plan.get("kind", "journey") == "journey" else [],
                "items": [{k: v for k, v in i.items() if k != "route"} for i in plan.get("items", [])],
                "recommendation": rec,
                "tokens": tokens,
                "autonomy_level": s.autonomy,
            },
        )
        if s.autonomy >= 2:
            s.pending = {"plan_id": plan["plan_id"], "kind": "plan"}
            yield self.emit(
                "approval_request",
                {
                    "plan_id": plan["plan_id"],
                    "risk": "high" if high else "low",
                    "options": [
                        {"id": "approve", "label": "Approve plan"},
                        {"id": "reject", "label": "Not now"},
                    ],
                    "reason": "Autonomy L2 asks before committing."
                    if s.autonomy == 2
                    else "Autopilot arms after you approve this plan.",
                },
            )

    # ------------------------------------------------------------------------------------------
    def _narrate(self, draft: Draft, plan: dict[str, Any] | None, rec: str) -> tuple[str, list, str, str]:
        """Narrator pass. Returns (resolved text, resolved tokens, token template, source)."""
        s = self.s
        persona = s.persona
        candidates: list[tuple[str, str]] = []
        defects: list[str] = []
        for _attempt in range(2):
            body = {
                "verified_draft": draft.text,
                "recommendation": rec,
                "user_request": s.user_text,
                "autonomy_level": s.autonomy,
            }
            if defects:
                body["fix"] = defects
            try:
                out = self.llm.chat(
                    [
                        {"role": "system", "content": narrator_prompt(persona)},
                        {"role": "user", "content": json.dumps(body, default=str)},
                    ],
                    temperature=0.3,
                )
            except LLMError:
                break
            text = (out.content or "").strip()
            defects = check_text(text, s.store, s.user_text)
            if text and not defects:
                candidates.append((text, "narrator"))
                break
        if not candidates:
            if not check_text(draft.text, s.store, s.user_text):
                candidates.append((draft.text, "draft"))
            else:
                candidates.append((template_message(persona, s.store, plan, rec, s.user_text), "template"))
        template, source = candidates[0]
        if s.autonomy == 1:
            template += " Advisor mode: I only suggest, nothing is committed."
        if plan is not None and plan.get("policy_acknowledged"):
            template += " Note: this conflicts with the midday break policy pack (MoHRE 2025 pack); please review it before committing."
        res = s.store.resolve(template)
        if res.unresolved:  # defensive: never ship a raw {{token}}
            template, source = template_message(persona, s.store, plan, rec, s.user_text), "template"
            res = s.store.resolve(template)
        if res.unresolved:
            template, _ = redact_bare_numbers(TOKEN_STRIP(template), s.user_text)
            res = s.store.resolve(template)
        return res.text, res.resolved, template, source

    # ------------------------------------------------------------------------------------------
    def approve(
        self, plan_id: str | None, approve: bool = True, undo_token: str | None = None
    ) -> Iterator[dict[str, Any]]:
        s = self.s
        if undo_token:
            yield from self.monitor.undo(undo_token)
            return
        pend = s.pending
        if not pend or (plan_id and pend["plan_id"] != plan_id):
            yield self.emit(
                "error", {"message": "There is nothing pending approval for that plan.", "recoverable": True}
            )
            return
        s.pending = None
        plan = s.plans[pend["plan_id"]]
        if not approve:
            yield self.emit(
                "message",
                {
                    "text": "Understood. I have not committed that plan; tell me what to change.",
                    "resolved": [],
                    "template": "",
                    "source": "system",
                },
            )
            return
        yield from self.commit(plan, auto=False, reason=pend.get("reason") or "Approved by the user.")

    def commit(
        self, plan: dict[str, Any], auto: bool, reason: str, undo_token: str | None = None
    ) -> Iterator[dict[str, Any]]:
        s = self.s
        plan["status"] = "committed"
        if s.store.has("weather"):  # the planner already saw the heat context for this plan
            plan["heat_checked"] = True
        s.active_plan_id = plan["plan_id"]
        s.store.set("plan", plan_summary(plan))
        payload: dict[str, Any] = {
            "plan_id": plan["plan_id"],
            "auto": auto,
            "reason": reason,
            "summary": plan_summary(plan),
            "autonomy_level": s.autonomy,
        }
        if undo_token:
            payload["undo_token"] = undo_token
        yield self.emit("plan_committed", payload)
        if not auto:
            yield self.emit(
                "monitor_tick",
                {
                    "sim_time": s.clock.now().isoformat(),
                    "status": "watching",
                    "note": "Monitor armed on the simulated clock.",
                },
            )


def TOKEN_STRIP(text: str) -> str:
    from .tokens import TOKEN_RE

    return TOKEN_RE.sub("", text)


__all__ = ["Agent", "Emitter", "get_persona", "plan_active_route"]

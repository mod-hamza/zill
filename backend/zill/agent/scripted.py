"""Scripted planner: a deterministic stand-in for the live model (used until an API key exists).

It issues REAL tool calls against the REAL tools and reads their results from the conversation to
decide the next step (flexible departure -> optimiser, crew -> policy check -> compliant re-plan), then
returns a draft with `{{tokens}}`. Narration is template-based. Sessions it produces are recorded with
`"live": false` and badged "Scripted session (live model not connected)" in the UI.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from zill import config

from .llm import ChatResult, ToolCall
from .narration import draft_text, template_message
from .personas import get_persona
from .prompts import role_of
from .session import Session

MODEL_NAME = "zill-scripted-planner"


def _tool_results(messages: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    """[(tool name, args, parsed result)] in call order, from the OpenAI-style message list."""
    calls: dict[str, tuple[str, dict[str, Any]]] = {}
    out: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for m in messages:
        if m.get("role") == "assistant":
            for tc in m.get("tool_calls") or []:
                calls[tc["id"]] = (tc["function"]["name"], json.loads(tc["function"]["arguments"] or "{}"))
        elif m.get("role") == "tool":
            name, args = calls.get(m["tool_call_id"], ("?", {}))
            try:
                res = json.loads(m["content"])
            except json.JSONDecodeError:
                res = {"ok": False}
            out.append((name, args, res))
    return out


class ScriptedLLM:
    scripted = True
    model = MODEL_NAME

    def __init__(self, session: Session, spec: dict[str, Any]) -> None:
        self.s = session
        self.spec = spec
        self._n = 0

    def available(self) -> bool:
        return True

    def status(self) -> dict[str, Any]:
        return {"available": True, "model": MODEL_NAME, "reason": "scripted"}

    # ------------------------------------------------------------------------------------------
    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: Any = None,
        model: str | None = None,
        temperature: float = 0.2,
    ) -> ChatResult:
        role = role_of(messages[0]["content"])
        if role == "narrator":
            body = json.loads(messages[-1]["content"])
            plan = self.s.draft_plan()
            return ChatResult(
                content=template_message(
                    self.s.persona, self.s.store, plan, body["recommendation"], self.s.user_text
                ),
                model=MODEL_NAME,
            )
        if role == "verifier":  # never called for scripted LLMs; refuse rather than rubber-stamp
            raise NotImplementedError("scripted LLM does not verify")
        return self._planner(messages)

    # ------------------------------------------------------------------------------------------
    def _call(self, note: str, name: str, args: dict[str, Any]) -> ChatResult:
        self._n += 1
        return ChatResult(
            content=note,
            model=MODEL_NAME,
            tool_calls=[ToolCall(id=f"call_{self._n}_{name}", name=name, arguments=args)],
        )

    def _planner(self, messages: list[dict[str, Any]]) -> ChatResult:
        sp, s = self.spec, self.s
        done = _tool_results(messages)
        names = [n for n, _, _ in done]
        mode, depart = sp.get("mode", get_persona(s.persona).default_mode), sp["depart"]
        sun = (sp.get("preference") or get_persona(s.persona).preference) == "sun"
        pref = {"preference": "sun"} if sun else {}
        if names.count("resolve_place") < 1:
            return self._call(
                "Locating where you are starting.",
                "resolve_place",
                {"query": sp["origin"], "role": "origin", "mode": mode},
            )
        if names.count("resolve_place") < 2:
            return self._call(
                "Locating your destination.",
                "resolve_place",
                {"query": sp["dest"], "role": "dest", "mode": mode},
            )
        if "get_weather" not in names:
            note = "Checking UV and the sky at your travel time."
            if not sun:
                note = "Checking the heat at your travel time."
            return self._call(note, "get_weather", {"at": depart})
        if "compare_routes" not in names:
            return self._call(
                "Comparing fastest, balanced and sunniest routes."
                if sun
                else "Comparing fastest, balanced and coolest routes.",
                "compare_routes",
                {
                    "origin": "origin",
                    "dest": "dest",
                    "mode": mode,
                    "depart_at": depart,
                    "latest_arrival": sp.get("latest_arrival"),
                    **pref,
                },
            )
        if sp.get("flexible") and "optimise_departure" not in names:
            win = {
                "start": depart,
                "end": (s.parse_time(depart) + timedelta(minutes=sp.get("window_min", 90))).isoformat(),
            }
            return self._call(
                "Your departure is flexible, so I will test later start times.",
                "optimise_departure",
                {
                    "origin": "origin",
                    "dest": "dest",
                    "mode": mode,
                    "window": win,
                    "latest_arrival": sp.get("latest_arrival"),
                    **pref,
                },
            )
        if sp.get("flexible") and "optimise_departure" in names and names.count("compare_routes") < 2:
            dep = s.store.get("departure") or {}
            best = (dep.get("best") or {}).get("depart")
            gain = (dep.get("sun_gained_s") or 0) >= 30 if sun else dep.get("rhl_saved_pct", 0) > 1.0
            if best and gain:
                return self._call(
                    "Re-running the comparison at the recommended departure.",
                    "compare_routes",
                    {
                        "origin": "origin",
                        "dest": "dest",
                        "mode": mode,
                        "depart_at": best,
                        "latest_arrival": sp.get("latest_arrival"),
                        "store_as": "route_best",
                        **pref,
                    },
                )
        if sp.get("cool_stops") and "find_cool_stops" not in names:
            return self._call(
                "Looking for a cool stop near the destination.",
                "find_cool_stops",
                {"near": "dest", "radius_m": 400, "type": "indoor"},
            )
        if get_persona(s.persona).policy_pack:
            n_pol = names.count("check_policy")
            if n_pol == 0:
                return self._call(
                    "Checking the plan against the midday-break policy pack.", "check_policy", {}
                )
            pol = s.store.get("policy") or {}
            if not pol.get("ok") and n_pol == 1 and pol.get("next_compliant"):
                nxt = pol["next_compliant"]
                end = (datetime.fromisoformat(nxt) + timedelta(minutes=60)).isoformat()
                if "optimise_departure" not in names[names.index("check_policy") :]:
                    return self._call(
                        "The plan falls inside the midday window; searching compliant departures.",
                        "optimise_departure",
                        {
                            "origin": "origin",
                            "dest": "dest",
                            "mode": mode,
                            "window": {"start": nxt, "end": end},
                        },
                    )
                if names.count("compare_routes") < 3:
                    best = (s.store.get("departure") or {}).get("best", {}).get("depart", nxt)
                    return self._call(
                        "Planning the move at the compliant departure.",
                        "compare_routes",
                        {
                            "origin": "origin",
                            "dest": "dest",
                            "mode": mode,
                            "depart_at": best,
                            "store_as": "route_compliant",
                        },
                    )
                return self._call("Re-checking the policy for the revised plan.", "check_policy", {})
        return self._final(done)

    def _final(self, done: list[tuple[str, dict[str, Any], dict[str, Any]]]) -> ChatResult:
        s = self.s
        plan = s.draft_plan()
        if plan is None:
            return ChatResult(
                content=json.dumps(
                    {
                        "plan_id": None,
                        "recommendation": "fastest",
                        "text": "I could not compute a route for that request.",
                    }
                ),
                model=MODEL_NAME,
            )
        routes = plan["routes"]
        fast = routes.get("fastest", {})
        tol = 0.15 if s.persona == "rider" else 0.25
        rec = "fastest"
        sun = plan.get("preference") == "sun"
        gain_key = "sun_gained_s" if sun else "sun_saved_s"
        for label in ("sunniest", "balanced") if sun else ("coolest", "balanced"):
            r = routes.get(label)
            if (
                r
                and (r.get(gain_key) or 0) >= 30
                and (r.get("added_time_s") or 0) <= tol * fast.get("duration_s", 0)
            ):
                rec = label
                break
        plan["recommendation"] = rec
        return ChatResult(
            content=json.dumps(
                {"plan_id": plan["plan_id"], "recommendation": rec, "text": draft_text(s.store, plan, rec)}
            ),
            model=MODEL_NAME,
        )


__all__ = ["ScriptedLLM", "config"]

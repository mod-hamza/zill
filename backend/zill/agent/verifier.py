"""Verifier (PRD 11.2.2): a deterministic layer plus a separate LLM call with its own system prompt.

The deterministic layer is the hard guarantee: every token resolves, no bare computed number, route
edges are valid for the mode, the arrival window holds, the policy pack is respected and qualitative
claims do not contradict the computed stats. The LLM layer (live only) adds semantic checking.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from . import policy as policy_mod
from .personas import get_persona
from .prompts import verifier_prompt
from .session import Session, plan_active_route
from .tokens import TOKEN_RE, ResultStore, count_claims, find_violations
from .tools import digest, plan_items


@dataclass
class Draft:
    text: str
    plan_id: str | None = None
    recommendation: str | None = None


@dataclass
class VerifyResult:
    checked: int = 0
    defects: list[str] = field(default_factory=list)
    layers: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.defects

    def payload(self) -> dict[str, Any]:
        return {
            "checked": self.checked,
            "passed": self.checked - min(len(self.defects), self.checked) if self.defects else self.checked,
            "defects": self.defects,
            "layers": self.layers,
        }


def parse_draft(content: str) -> Draft:
    """The planner replies with JSON {plan_id, recommendation, text}; tolerate fences and prose."""
    s = (content or "").strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s)
    cands = [s]
    m = re.search(r"\{.*\}", s, re.S)
    if m:
        cands.append(m.group(0))
    for cand in cands:
        try:
            obj = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "text" in obj:
            return Draft(str(obj["text"]), obj.get("plan_id"), obj.get("recommendation"))
    return Draft(text=s)


_SAVES = re.compile(r"\b(saves?|less sun|cooler|shadier|more shade|spares?)\b", re.I)
_QUICKER = re.compile(r"\b(faster|quicker|shorter|no extra time|no added time)\b", re.I)


def verify_deterministic(s: Session, draft: Draft, user_text: str) -> VerifyResult:
    res = VerifyResult(layers=["deterministic"])
    store: ResultStore = s.store
    if not draft.text.strip():
        res.defects.append("draft text is empty")
        return res
    # 1. tokens resolve, no bare numbers
    tokens = TOKEN_RE.findall(draft.text)
    res.checked += max(count_claims(draft.text), 0)
    for t in dict.fromkeys(tokens):
        try:
            store.resolve_path(t)
        except Exception:
            res.defects.append(f"unresolved token {{{{{t}}}}}")
    for bad in find_violations(draft.text, user_text):
        res.checked += 1
        res.defects.append(f"bare number '{bad}' must be a {{{{token}}}}")
    # 2. plan exists and recommendation is one of its routes
    plan = s.plans.get(draft.plan_id or s.draft_plan_id or "")
    if plan is None:
        res.checked += 1
        res.defects.append("draft refers to no plan produced by a tool")
        return res
    rec = draft.recommendation or plan.get("recommendation")
    if plan.get("kind", "journey") == "journey":
        res.checked += 1
        if rec not in plan["routes"]:
            res.defects.append(
                f"recommendation '{rec}' is not one of the computed routes {list(plan['routes'])}"
            )
            return res
    route = plan["routes"].get(rec) if rec else plan_active_route(plan)
    # 3. edges valid for the mode
    if route is not None and plan.get("kind", "journey") == "journey":
        res.checked += 1
        for d in s.backend.validate_route(route, plan["mode"]):
            res.defects.append(d)
    # 4. arrival window
    la = plan.get("latest_arrival")
    if la and route is not None:
        res.checked += 1
        if datetime.fromisoformat(route["arrive"]) > datetime.fromisoformat(la):
            res.defects.append("recommended route arrives after the user's latest arrival")
    # 5. policy pack
    pack = get_persona(s.persona).policy_pack
    if pack:
        res.checked += 1
        check = policy_mod.check_policy(
            {"items": plan_items({**plan, "recommendation": rec}), "persona": s.persona}, pack
        )
        if not check["ok"] and not plan.get("policy_acknowledged"):
            res.defects.append(
                f"plan conflicts with {check['label']} ({check['count']} conflict(s)); "
                "re-plan outside the midday window or flag the conflict explicitly"
            )
    # 6. qualitative claims vs computed stats
    if route is not None:
        res.checked += 1
        if _SAVES.search(draft.text) and rec != "fastest" and (route.get("sun_saved_s") or 0) <= 0:
            res.defects.append(
                "text claims sun savings but the recommended route saves no sun versus fastest"
            )
        if _QUICKER.search(draft.text) and rec != "fastest" and (route.get("added_time_s") or 0) > 0:
            res.defects.append("text claims no extra time but the recommended route is slower than fastest")
    return res


def verify_llm(llm: Any, s: Session, draft: Draft, user_text: str) -> VerifyResult:
    """Separate call, separate system prompt: semantic check against raw tool results."""
    plan = s.plans.get(draft.plan_id or s.draft_plan_id or "") or {}
    body = {
        "user_request": user_text,
        "draft_text": draft.text,
        "recommendation": draft.recommendation,
        "plan": digest({k: v for k, v in plan.items() if k != "items"}),
        "tool_results": digest(s.store.snapshot()),
    }
    out = llm.chat(
        [
            {"role": "system", "content": verifier_prompt()},
            {"role": "user", "content": json.dumps(body, default=str)},
        ],
        temperature=0.0,
    )
    res = VerifyResult(layers=["llm"])
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", (out.content or "").strip())
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        obj = json.loads(m.group(0)) if m else None
    if not isinstance(obj, dict):
        res.defects.append("verifier returned an unreadable verdict")
        return res
    res.checked = int(obj.get("claims_checked") or 0)
    for d in obj.get("defects") or []:
        res.defects.append(
            f"{d.get('claim', 'claim')}: {d.get('issue', 'unsupported')}" if isinstance(d, dict) else str(d)
        )
    if obj.get("passed") is False and not res.defects:
        res.defects.append("verifier rejected the draft without details")
    return res


def merge(a: VerifyResult, b: VerifyResult) -> VerifyResult:
    return VerifyResult(
        checked=max(a.checked, 0) + max(b.checked, 0),
        defects=a.defects + b.defects,
        layers=a.layers + b.layers,
    )

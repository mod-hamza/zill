# ruff: noqa: E501
"""Deterministic text templates: the scripted Planner draft, the scripted Narrator, and fallbacks.

All computed numbers are `{{tokens}}`; the choice of which sentences appear depends on the actual
values in the ResultStore (e.g. a modest saving is reported as modest, never inflated).
"""

from __future__ import annotations

from typing import Any

from .tokens import ResultStore

MODE_WORD = {"walk": "walk", "cycle": "ride", "scooter": "ride"}
MODE_ING = {"walk": "walking", "cycle": "cycling", "scooter": "riding"}
LIMITS = "Shade counts buildings, mapped trees and covered links only; awnings and wind are not modelled."


def _facts(store: ResultStore, plan: dict[str, Any] | None, rec: str) -> dict[str, Any]:
    K = (plan or {}).get("route_key", "route")
    entry = store.get(K) or {}
    r = entry.get(rec) or {}
    f = entry.get("fastest") or {}
    dep = store.get("departure") or {}
    best, first = dep.get("best") or {}, dep.get("first") or {}
    return {
        "K": K,
        "r": r,
        "f": f,
        "c": entry.get("coolest") or {},
        "rec": rec,
        "mode": (plan or {}).get("mode", "walk"),
        "saved_s": r.get("sun_saved_s") or 0.0,
        "added_s": r.get("added_time_s") or 0.0,
        "indoor": r.get("indoor_pct") or 0.0,
        "covered": r.get("covered_pct") or 0.0,
        "dep_gain": (dep.get("rhl_saved_pct") or 0.0) if best.get("depart") != first.get("depart") else 0.0,
        "weather": store.get("weather") or {},
        "stops": store.get("stops") or {},
        "policy": store.get("policy") or {},
        "day": store.get("day"),
        "moved": bool(plan and plan.get("route_key", "route") != "route" and (store.get("route") or {}).get("depart")
                      and (store.get("route") or {}).get("depart") != r.get("depart")),
        "why": ((dep.get("why") or {}).get("changes") or []) if isinstance(dep.get("why"), dict) else [],
    }


def _sun_sentence(F: dict[str, Any]) -> str:
    K, rec = F["K"], F["rec"]
    if rec == "fastest":
        base = (
            f"The fastest {MODE_WORD[F['mode']]} spends {{{{{K}.fastest.sun_exposure_min}}}} in direct sun."
        )
        c = F.get("c") or {}
        if c and (c.get("sun_saved_s") or 0) < 30:
            return base + (
                f" The coolest option would save only {{{{{K}.coolest.sun_saved_min}}}} of sun, so the saving on "
                "the route itself is small and the fastest is the better trade."
            )
        if c:
            return base + (
                f" The coolest option saves {{{{{K}.coolest.sun_saved_min}}}} of sun but adds "
                f"{{{{{K}.coolest.added_time_min}}}}, which is more time than I would trade for it."
            )
        return base
    if F["saved_s"] >= 30:
        return (
            f"The {rec} {MODE_WORD[F['mode']]} spends {{{{{K}.{rec}.sun_exposure_min}}}} in direct sun against "
            f"{{{{{K}.fastest.sun_exposure_min}}}} on the fastest, saving {{{{{K}.{rec}.sun_saved_min}}}} of sun, and "
            f"{{{{{K}.{rec}.shaded_pct}}}} of it is shaded."
        )
    return (
        f"The fastest route is already close to as shaded as this trip gets: the {rec} option spends "
        f"{{{{{K}.{rec}.sun_exposure_min}}}} in direct sun against {{{{{K}.fastest.sun_exposure_min}}}}, "
        "so the saving on the route itself is small."
    )


def _extras(F: dict[str, Any]) -> list[str]:
    K, rec = F["K"], F["rec"]
    out: list[str] = []
    if rec != "fastest":
        if F["added_s"] > 1:
            out.append(f"It takes {{{{{K}.{rec}.added_time_min}}}} longer than the fastest.")
        else:
            out.append("It takes no longer than the fastest.")
    if F["indoor"] > 0.5:
        out.append(f"{{{{{K}.{rec}.indoor_pct}}}} of it is indoors or on air-conditioned links.")
    elif F["covered"] > 0.5:
        out.append(f"{{{{{K}.{rec}.covered_pct}}}} of it is under cover.")
    if F["dep_gain"] > 1.0:
        out.append(
            "Leaving at {{departure.best.depart_time}} instead of {{departure.first.depart_time}} lowers the "
            "heat-load index by {{departure.rhl_saved_pct}} (model estimate, not a measurement)."
        )
    if F["dep_gain"] > 1.0 and F["why"] and F["why"][0].get("street"):
        way = "falls into shade" if F["why"][0].get("direction") == "into_shade" else "moves into sun"
        out.append(
            f"Why: {{{{departure.why.changes.0.street}}}} {way} around {{{{departure.why.changes.0.at}}}}."
        )
    w = F["weather"]
    if w.get("heat_alert"):
        out.append("There is a heat alert: carry water and take shade breaks.")
    elif w.get("apparent_c") is not None:
        out.append("It feels like {{weather.apparent_c}} then.")
    st = F["stops"]
    if st.get("nearest"):
        out.append("Nearest cool stop: {{stops.nearest.name}}, {{stops.nearest.distance_m}} away.")
    pol = F["policy"]
    if pol:
        if pol.get("ok") and F["moved"]:
            out.append(
                "I moved this from {{route.depart_time}} to {{" + K + "." + rec + ".depart_time}} because "
                "{{policy.label}} bars outdoor work in direct sun between {{policy.midday_window_start}} and "
                "{{policy.midday_window_end}}; the new timing has no conflict. Please verify the rule before relying on it."
            )
        elif pol.get("ok"):
            out.append("{{policy.label}}: no conflict with this timing.")
        else:
            out.append("{{policy.label}}: this timing conflicts with the midday window.")
    return out


def draft_text(store: ResultStore, plan: dict[str, Any] | None, rec: str) -> str:
    """The scripted Planner's proposal text (neutral, operational)."""
    F = _facts(store, plan, rec)
    K = F["K"]
    if F["day"]:
        return (
            "Proposed day plan in order: {{day.order.0}}, {{day.order.1}}. Cool-down breaks inserted: "
            "{{day.totals.breaks}}. " + LIMITS
        )
    head = (
        f"Recommended: the {rec} {MODE_WORD[F['mode']]} from {{{{{K}.origin}}}} to {{{{{K}.dest}}}}, leaving "
        f"{{{{{K}.{rec}.depart_time}}}}."
    )
    return " ".join([head, _sun_sentence(F), *_extras(F), LIMITS])


def template_message(
    persona: str, store: ResultStore, plan: dict[str, Any] | None, rec: str, user_text: str = ""
) -> str:
    """Persona-toned final message built from tokens (scripted Narrator and last-resort fallback)."""
    F = _facts(store, plan, rec)
    K = F["K"]
    if F["day"]:
        return draft_text(store, plan, rec)
    ing = MODE_ING[F["mode"]]
    if persona == "rider":
        parts = [
            f"Take the {rec} route, {{{{{K}.origin}}}} to {{{{{K}.dest}}}}, leave {{{{{K}.{rec}.depart_time}}}}.",
            _sun_sentence(F),
            *_extras(F),
        ]
    elif persona == "crew":
        parts = [
            f"Movement plan: {{{{{K}.origin}}}} to {{{{{K}.dest}}}} by the {rec} route, leaving "
            f"{{{{{K}.{rec}.depart_time}}}}, arriving {{{{{K}.{rec}.arrive_time}}}}.",
            _sun_sentence(F),
            *_extras(F),
        ]
    else:
        parts = [
            f"Here is what I would do. Go {ing} from {{{{{K}.origin}}}} to {{{{{K}.dest}}}} by the {rec} route, "
            f"leaving at {{{{{K}.{rec}.depart_time}}}}.",
            _sun_sentence(F),
            *_extras(F),
        ]
    parts.append(LIMITS)
    return " ".join(parts)


def replan_message(store: ResultStore, auto: bool, kind: str) -> str:
    rp = store.get("replan") or {}
    lead = {
        "delay": "Your departure slipped by {{replan.delay_min}}, so I re-checked the shade for the new time.",
        "closure": "A closure blocks part of your route, so I searched for a way around it.",
        "heat_alert": "A heat alert is active at your travel time, so I re-planned for more shade and cover.",
    }.get(kind, "Conditions changed, so I re-checked your plan.")
    if rp.get("blocked"):
        return lead + " I could not find an alternative route; please review before moving."
    base = "your delayed plan" if kind == "delay" else "your original plan"
    if abs(rp.get("delta_arrival_s") or 0.0) < 30:
        arr = f" New arrival {{{{replan.new.arrive_time}}}}, the same as {base}."
    else:
        arr = f" New arrival {{{{replan.new.arrive_time}}}}, which is {{{{replan.delta_arrival_min}}}} against {base}."
    rhl = (
        " Heat-load index is {{replan.delta_rhl_pct}} against the plan as first made."
        if abs(rp.get("delta_rhl_pct") or 0.0) >= 0.5
        else " Heat-load index is unchanged."
    )
    body = arr + rhl
    tail = (
        " Applied automatically under Autopilot because the change is small. You can undo it."
        if auto
        else " The change is larger than my standing permission, so I need your approval before applying it."
    )
    return lead + body + tail

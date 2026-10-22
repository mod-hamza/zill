# ruff: noqa: E501
"""Planner -> Verifier -> Narrator loop and the proactive Monitor (synthetic backend, real orchestration)."""

from __future__ import annotations

import json

import pytest

from tests.agent_fakes import SyntheticBackend
from zill.agent.llm import ChatResult, FakeLLM, ToolCall
from zill.agent.orchestrator import Agent
from zill.agent.scripted import ScriptedLLM
from zill.agent.session import Session, SimClock
from zill.agent.tokens import find_violations

TOURIST = {
    "persona": "tourist",
    "origin": "metro",
    "dest": "opera",
    "mode": "walk",
    "depart": "13:30",
    "flexible": True,
    "cool_stops": True,
}
PROMPT = "Metro to the Opera, 13:30, I'm walking"


def mk(persona="tourist", autonomy=2, spec=None, backend=None):
    s = Session(persona=persona, backend=backend or SyntheticBackend(), date_key="summer", autonomy=autonomy)
    s.clock = SimClock(s.parse_time("13:00"), rate=0.0)
    agent = Agent(s, ScriptedLLM(s, spec or TOURIST))
    return s, agent


def types(events):
    return [e["type"] for e in events]


def run(agent, text=PROMPT):
    return list(agent.run_turn(text))


def test_tourist_turn_event_sequence_and_message():
    s, agent = mk(autonomy=2)
    ev = run(agent)
    t = types(ev)
    assert t[0] == "session_started"
    assert t.index("tool_call") < t.index("tool_result") < t.index("verifier") < t.index("proposal")
    assert t.index("proposal") < t.index("approval_request") < t.index("message") == len(t) - 1
    # ids unique, ordered, ts present, payload dict
    assert len({e["id"] for e in ev}) == len(ev) and all(
        e["ts"] and isinstance(e["payload"], dict) for e in ev
    )
    names = [e["payload"]["name"] for e in ev if e["type"] == "tool_call"]
    assert (
        names[:2] == ["resolve_place", "resolve_place"]
        and "compare_routes" in names
        and "optimise_departure" in names
    )
    msg = ev[-1]["payload"]
    assert "{{" not in msg["text"] and msg["resolved"] and "{{" in msg["template"]
    assert find_violations(msg["template"], PROMPT) == []  # no bare computed numbers authored
    ver = next(e for e in ev if e["type"] == "verifier")["payload"]
    assert ver["defects"] == [] and ver["checked"] >= 5 and ver["layers"] == ["deterministic"]
    prop = next(e for e in ev if e["type"] == "proposal")["payload"]
    assert {r["label"] for r in prop["routes"]} == {"fastest", "balanced", "coolest"} and prop["tokens"]
    assert s.active_plan is None and s.pending["plan_id"] == prop["plan_id"]


def test_thoughts_are_short_summaries_without_numbers():
    _, agent = mk()
    for e in run(agent):
        if e["type"] == "thought":
            assert len(e["payload"]["text"]) <= 240 and find_violations(e["payload"]["text"], PROMPT) == []


def test_approval_commits_plan_l2():
    s, agent = mk(autonomy=2)
    run(agent)
    ev = list(agent.approve(s.pending["plan_id"], True))
    assert types(ev) == ["plan_committed", "monitor_tick"]
    assert s.active_plan_id and s.active_plan["status"] == "committed"
    assert s.store.resolve_path("plan.arrive_time")
    # nothing pending twice
    assert types(list(agent.approve("plan_1", True))) == ["error"]


def test_reject_does_not_commit():
    s, agent = mk(autonomy=2)
    run(agent)
    ev = list(agent.approve(s.pending["plan_id"], False))
    assert types(ev) == ["message"] and s.active_plan_id is None


def test_l1_advisor_never_asks_or_commits():
    s, agent = mk(autonomy=1)
    ev = run(agent)
    assert "approval_request" not in types(ev) and s.pending is None
    assert "Advisor mode" in ev[-1]["payload"]["text"]
    assert types(list(agent.approve("plan_1", True))) == ["error"]
    assert s.active_plan_id is None


def test_modest_saving_reported_honestly():
    """When the coolest route saves little, the text must say so rather than inflate."""
    s, agent = mk(spec={**TOURIST, "depart": "07:00", "flexible": False, "cool_stops": False})
    ev = run(agent, "Metro to the Opera, 07:00, I'm walking")
    text = ev[-1]["payload"]["text"]
    assert ev[-1]["type"] == "message" and "{{" not in text
    rec = next(e for e in ev if e["type"] == "proposal")["payload"]["recommendation"]
    saved = s.plans[s.draft_plan_id]["routes"]["coolest"]["sun_saved_s"]
    if saved < 30:
        assert rec == "fastest" and "small" in text


# ------------------------------------------------------------------ live-style loop with FakeLLM
def tc(name, args, i=1):
    return ToolCall(id=f"c{i}_{name}", name=name, arguments=args)


def planner_script(text, rec="coolest"):
    return [
        ChatResult(
            content="Resolving both places.",
            tool_calls=[
                tc("resolve_place", {"query": "metro", "role": "origin"}, 1),
                tc("resolve_place", {"query": "opera", "role": "dest"}, 2),
            ],
        ),
        ChatResult(
            tool_calls=[tc("compare_routes", {"origin": "origin", "dest": "dest", "depart_at": "13:30"}, 3)]
        ),
        lambda m, t: ChatResult(
            content=json.dumps({"plan_id": "plan_1", "recommendation": rec, "text": text})
        ),
    ]


GOOD = (
    "The coolest walk saves {{route.coolest.sun_saved_min}} of sun and arrives {{route.coolest.arrive_time}}."
)
VERDICT_OK = json.dumps({"passed": True, "claims_checked": 7, "defects": []})


def live_agent(script, autonomy=2):
    s = Session(persona="tourist", backend=SyntheticBackend(), date_key="summer", autonomy=autonomy)
    llm = FakeLLM(script)
    return s, llm, Agent(s, llm)


def test_live_path_runs_llm_verifier_and_narrator():
    narr = "Take the shaded route; it saves {{route.coolest.sun_saved_min}} of sun."
    s, llm, agent = live_agent(planner_script(GOOD) + [VERDICT_OK, narr])
    ev = run(agent)
    ver = next(e for e in ev if e["type"] == "verifier")["payload"]
    assert ver["layers"] == ["deterministic", "llm"] and ver["defects"] == []
    msg = ev[-1]["payload"]
    assert msg["source"] == "narrator" and msg["text"].startswith("Take the shaded route; it saves ")
    # three distinct system prompts: planner, verifier, narrator
    roles = [c["messages"][0]["content"].split("\n")[0] for c in llm.calls]
    assert (
        roles[0].startswith("ROLE:PLANNER")
        and "ROLE:VERIFIER v1" in roles
        and any(r.startswith("ROLE:NARRATOR") for r in roles)
    )


def test_bare_number_in_draft_triggers_fix_round_then_passes():
    bad = "The coolest walk saves about 5 minutes of sun."
    script = planner_script(bad)[:2] + [
        lambda m, t: ChatResult(
            content=json.dumps({"plan_id": "plan_1", "recommendation": "coolest", "text": bad})
        ),
        lambda m, t: ChatResult(
            content=json.dumps({"plan_id": "plan_1", "recommendation": "coolest", "text": GOOD})
        ),
        VERDICT_OK,
        "Shady and quick: {{route.coolest.sun_saved_min}} less sun.",
    ]
    s, llm, agent = live_agent(script)
    ev = run(agent)
    verifiers = [e["payload"] for e in ev if e["type"] == "verifier"]
    assert len(verifiers) == 2 and verifiers[0]["defects"] and "bare number" in verifiers[0]["defects"][0]
    assert verifiers[1]["defects"] == []
    # the defects were fed back to the planner
    fix_msg = llm.calls[3]["messages"][-1]["content"]
    assert "VERIFIER DEFECTS" in fix_msg and "bare number" in fix_msg
    assert ev[-1]["type"] == "message"


def test_unresolved_token_rejected_after_max_rounds_gives_error():
    bad = "Saves {{route.coolest.does_not_exist}}."
    def fix(m, t):
        return ChatResult(
            content=json.dumps({"plan_id": "plan_1", "recommendation": "coolest", "text": bad})
        )  # noqa: E731
    s, llm, agent = live_agent(planner_script(bad)[:2] + [fix, fix, fix])
    ev = run(agent)
    assert types(ev)[-1] == "error" and "message" not in types(ev)
    assert [e["type"] for e in ev].count("verifier") == 3  # initial + 2 fix rounds (max)


def test_llm_verifier_defect_blocks_and_is_surfaced():
    verdict = json.dumps(
        {
            "passed": False,
            "claims_checked": 3,
            "defects": [{"claim": "arrives on time", "issue": "no arrival constraint was checked"}],
        }
    )
    s, llm, agent = live_agent(
        planner_script(GOOD)
        + [
            verdict,
            lambda m, t: ChatResult(
                content=json.dumps({"plan_id": "plan_1", "recommendation": "coolest", "text": GOOD})
            ),
            VERDICT_OK,
            "Fine: {{route.coolest.sun_saved_min}}.",
        ]
    )
    ev = run(agent)
    v = [e["payload"] for e in ev if e["type"] == "verifier"]
    assert v[0]["defects"] and "arrives on time" in v[0]["defects"][0] and v[1]["defects"] == []


def test_narrator_bare_numbers_fall_back_to_verified_draft():
    s, llm, agent = live_agent(
        planner_script(GOOD) + [VERDICT_OK, "It saves 5 minutes!", "Still about 5 minutes."]
    )
    ev = run(agent)
    msg = ev[-1]["payload"]
    assert msg["source"] == "draft" and "5 minutes" not in msg["text"] and "{{" not in msg["text"]


def test_llm_outage_is_reported_not_raised():
    s, llm, agent = live_agent([])  # exhausted script raises LLMError
    ev = run(agent)
    assert types(ev)[-1] == "error" and ev[-1]["payload"]["recoverable"]


def test_tool_arguments_error_is_recoverable():
    bad_call = ToolCall(
        id="c1", name="compare_routes", arguments={}, arguments_error="unparseable tool arguments"
    )
    script = [ChatResult(tool_calls=[bad_call])] + planner_script(GOOD)
    s, llm, agent = live_agent(script + [VERDICT_OK, "ok {{route.coolest.sun_saved_min}}"])
    ev = run(agent)
    tr = next(e for e in ev if e["type"] == "tool_result")["payload"]
    assert tr["ok"] is False and ev[-1]["type"] == "message"


# ------------------------------------------------------------------ verifier constraints
def test_arrival_window_defect_via_scripted_planner():
    # latest arrival 13:35 is impossible for a 15-minute walk at 13:30: compare_routes still returns routes,
    # but the verifier must refuse to approve a recommendation that arrives late
    s, agent = mk(spec={**TOURIST, "flexible": False, "cool_stops": False, "latest_arrival": "13:35"})
    ev = run(agent, "Metro to the Opera, 13:30, I'm walking, must arrive by 13:35")
    vs = [e for e in ev if e["type"] == "verifier"]
    assert vs and any("latest arrival" in d for d in vs[0]["payload"]["defects"])
    assert types(ev)[-1] == "error"


def test_stairs_forbidden_for_cycle_is_a_defect():
    be = SyntheticBackend(stairs_edges={1, 4})  # both corridors have stairs
    s, agent = mk(
        "rider",
        backend=be,
        spec={"persona": "rider", "origin": "metro", "dest": "opera", "mode": "cycle", "depart": "13:30"},
    )
    ev = run(agent, "Metro to the Opera by bike")
    v = next(e for e in ev if e["type"] == "verifier")["payload"]
    assert any("stairs" in d for d in v["defects"])


def test_crew_midday_conflict_is_replanned_compliant():
    spec = {"persona": "crew", "origin": "metro", "dest": "opera", "mode": "walk", "depart": "13:30"}
    s, agent = mk("crew", spec=spec)
    ev = run(agent, "Move the crew from the metro to the opera at 13:30")
    names = [e["payload"]["name"] for e in ev if e["type"] == "tool_call"]
    assert names.count("check_policy") == 2 and "optimise_departure" in names
    ver = next(e for e in ev if e["type"] == "verifier")["payload"]
    assert ver["defects"] == []
    route = s.plans[s.draft_plan_id]["routes"][s.plans[s.draft_plan_id]["recommendation"]]
    assert route["depart"] >= "2026-07-15T15:00"
    assert s.store.get("policy")["ok"] and s.store.get("policy")["verified"] is False
    assert "unverified" in ev[-1]["payload"]["text"].lower() or "verify" in ev[-1]["payload"]["text"].lower()


def test_crew_policy_conflict_flagged_when_unfixable():
    """If the planner keeps proposing a conflicting plan, the user sees an explicit warning."""
    s = Session(persona="crew", backend=SyntheticBackend(), date_key="summer", autonomy=2)
    conflicting = planner_script("Crew moves at {{route.fastest.depart_time}}.", rec="fastest")
    def fix(m, t):
        return ChatResult(
            content=json.dumps(
                {
                    "plan_id": "plan_1",
                    "recommendation": "fastest",  # noqa: E731
                    "text": "Crew moves at {{route.fastest.depart_time}}.",
                }
            )
        )
    llm = FakeLLM(conflicting + [fix, fix, VERDICT_OK, "Crew moves at {{route.fastest.depart_time}}."])
    ev = list(Agent(s, llm).run_turn("Crew move at 13:30"))
    assert ev[-1]["type"] == "message" and "conflicts with the midday break" in ev[-1]["payload"]["text"]
    appr = next(e for e in ev if e["type"] == "approval_request")["payload"]
    assert appr["risk"] == "high"


# ------------------------------------------------------------------ Monitor
def committed(autonomy=3, **kw):
    s, agent = mk(autonomy=autonomy, **kw)
    run(agent)
    list(agent.approve(s.pending["plan_id"], True))
    return s, agent


def test_l3_auto_applies_small_delay_replan_with_undo():
    s, agent = committed(3)
    old_id, old_arrive = s.active_plan_id, s.active_plan["routes"][s.active_plan["recommendation"]]["arrive"]
    ev = list(agent.monitor.simulate("delay", {"minutes": 20}))
    t = types(ev)
    assert t[:2] == ["monitor_tick", "replan"] and "plan_committed" in t and "approval_request" not in t
    rp = next(e for e in ev if e["type"] == "replan")["payload"]
    assert (
        rp["auto"] is True and abs(rp["diff"]["delta_arrival_s"]) <= 600 and rp["diff"]["delta_rhl_pct"] <= 10
    )
    assert rp["diff"]["delay_s"] == 1200 and rp["diff"]["delta_arrival_vs_committed_s"] >= 1000
    pc = next(e for e in ev if e["type"] == "plan_committed")["payload"]
    assert pc["auto"] and pc["undo_token"] and pc["reason"]
    assert s.active_plan_id != old_id and s.autonomy_log[-1]["undo_token"] == pc["undo_token"]
    msg = ev[-1]["payload"]
    assert ev[-1]["type"] == "message" and "Applied automatically" in msg["text"] and "{{" not in msg["text"]
    assert find_violations(msg["template"], "") == []
    # undo
    ev2 = list(agent.approve(None, True, undo_token=pc["undo_token"]))
    assert ev2[0]["type"] == "plan_committed" and ev2[0]["payload"]["undo"] and s.active_plan_id == old_id
    assert s.active_plan["routes"][s.active_plan["recommendation"]]["arrive"] == old_arrive
    assert types(list(agent.approve(None, True, undo_token=pc["undo_token"]))) == [
        "error"
    ]  # token is single-use


def test_l3_large_rhl_change_requires_approval(monkeypatch):
    s, agent = committed(3)
    s.conditions.clear()
    # delay into the late afternoon: shade conditions differ a lot -> push beyond the +10% RHL limit by shrinking it
    monkeypatch.setattr("zill.config.AUTO_APPLY_MAX_RHL_INCREASE_PCT", -99.0)
    ev = list(agent.monitor.simulate("delay", {"minutes": 20}))
    t = types(ev)
    assert "approval_request" in t and "plan_committed" not in t
    assert next(e for e in ev if e["type"] == "replan")["payload"]["auto"] is False
    assert s.pending["kind"] == "replan"
    assert "need your approval" in ev[-1]["payload"]["text"]
    ev2 = list(agent.approve(s.pending["plan_id"], True))
    assert ev2[0]["type"] == "plan_committed" and not ev2[0]["payload"]["auto"]


def test_l2_always_asks_even_for_small_change():
    s, agent = committed(2)
    ev = list(agent.monitor.simulate("delay", {"minutes": 5}))
    assert "approval_request" in types(ev) and "plan_committed" not in types(ev)


def test_l1_advisor_replan_changes_nothing():
    s, agent = mk(autonomy=1)
    run(agent)
    s.active_plan_id = s.draft_plan_id  # as if the user had committed manually
    s.plans[s.active_plan_id]["status"] = "committed"
    before = s.active_plan_id
    ev = list(agent.monitor.simulate("delay", {"minutes": 20}))
    assert (
        "approval_request" not in types(ev)
        and "plan_committed" not in types(ev)
        and s.active_plan_id == before
    )
    assert "I only suggest" in ev[-1]["payload"]["text"]


def test_closure_on_route_forces_detour_and_unrelated_closure_is_ignored():
    s, agent = committed(3)
    ev = list(agent.monitor.simulate("closure", {"edge": 99}))
    assert "replan" not in types(ev) and ev[-1]["payload"]["status"] == "on_track"
    rec_route = s.active_plan["routes"][s.active_plan["recommendation"]]
    on_route = rec_route["edges"][0]
    ev = list(agent.monitor.simulate("closure", {"edge": on_route}))
    rp = next(e for e in ev if e["type"] == "replan")["payload"]
    assert rp["diff"]["route_changed"] is True


def test_closure_with_no_alternative_is_reported():
    s, agent = committed(3)
    on = s.active_plan["routes"][s.active_plan["recommendation"]]["edges"][0]
    other = 1 if on >= 4 else 4
    s.conditions.append({"type": "closure", "edge": other, "handled": True})
    ev = list(agent.monitor.simulate("closure", {"edge": on}))
    rp = next(e for e in ev if e["type"] == "replan")["payload"]
    assert rp["diff"]["blocked"] and "could not find an alternative" in ev[-1]["payload"]["text"]


def test_heat_alert_prefers_coolest():
    s, agent = committed(3, spec={**TOURIST, "flexible": False, "cool_stops": False})
    ev = list(agent.monitor.simulate("heat_alert", {}))
    if s.active_plan["recommendation"] == "coolest":  # already the coolest option: noted, nothing to change
        assert "replan" not in types(ev) and "already uses the coolest" in ev[-1]["payload"]["text"]
    s.active_plan["recommendation"] = "balanced"
    s.conditions.clear()
    ev = list(agent.monitor.simulate("heat_alert", {}))
    rp = next(e for e in ev if e["type"] == "replan")["payload"]
    assert rp["kind"] == "heat_alert" and "heat alert" in ev[-1]["payload"]["text"].lower()
    assert next(e for e in ev if e["type"] == "replan")["payload"]["new_plan_id"]


def test_monitor_ticks_on_simulated_clock_and_no_plan_is_idle():
    s, agent = mk()
    assert list(agent.monitor.tick())[0]["payload"]["status"] == "idle"
    s2, a2 = committed(3)
    t0 = s2.clock.now()
    ev = list(a2.monitor.simulate("sun_clock_jump", {"minutes": 30}))
    assert (s2.clock.now() - t0).total_seconds() == 1800 and ev[0]["payload"]["status"] in (
        "on_track",
        "deviation",
        "replanned",
    )
    with pytest.raises((TypeError, ValueError)):
        s2.clock.jump("nonsense")  # type: ignore[arg-type]
        s2.clock.now()


def test_simulated_clock_rate_default_x60():
    t = [0.0]
    base = Session(persona="tourist", backend=SyntheticBackend()).parse_time("13:00")
    c = SimClock(base, real=lambda: t[0])
    t[0] = 10.0
    assert (c.now() - base).total_seconds() == 600  # 10 real seconds = 10 sim minutes
    c.jump(base)
    t[0] = 11.0
    assert (c.now() - base).total_seconds() == 60

# ruff: noqa: E501
"""Sun mode in the agent (overnight Stream A): preference through the tools, the daylight-seeker persona,
sun / well-being tokens, verifier rules, and the shipped daylight_seeker replay (checked against hero.json)."""

from __future__ import annotations

import json

import pytest

from tests.synth_fixtures import synth_ctx, synth_env  # noqa: F401
from zill import config
from zill.agent import replay, tools
from zill.agent.backend import ServicesBackend
from zill.agent.orchestrator import Agent
from zill.agent.personas import get_persona
from zill.agent.prompts import planner_prompt
from zill.agent.scripted import ScriptedLLM
from zill.agent.session import Session, SimClock
from zill.agent.tokens import find_violations
from zill.agent.verifier import Draft, verify_deterministic

SPEC = {
    "persona": "daylight_seeker",
    "origin": "North East Tower",
    "dest": "Arcade Mall",
    "mode": "walk",
    "depart": "14:30",
    "flexible": False,
    "cool_stops": False,
    "preference": "sun",
}
PROMPT = "A sunny walk from North East Tower to Arcade Mall at 14:30 please, I want daylight."


@pytest.fixture()
def sess(synth_env, monkeypatch):  # noqa: F811
    monkeypatch.setenv("ZILL_WEATHER_LIVE", "0")

    def mk(persona="daylight_seeker"):
        s = Session(
            persona=persona, backend=ServicesBackend("synth"), date_key="summer", city="synth", autonomy=2
        )
        s.clock = SimClock(s.parse_time("14:30"), rate=0.0)
        return s

    return mk


def _compare(s, **kw):
    for q, role in (("North East Tower", "origin"), ("Arcade Mall", "dest")):
        assert tools.execute(s, "resolve_place", {"query": q, "role": role})[0]["ok"]
    res, _ = tools.execute(
        s, "compare_routes", {"origin": "origin", "dest": "dest", "depart_at": "14:30", **kw}
    )
    assert res["ok"], res
    return res


def test_persona_defaults_to_sun_and_tools_store_sunniest_and_wellbeing(sess):
    assert get_persona("daylight_seeker").preference == "sun" and get_persona("tourist").preference == "shade"
    s = sess()
    res = _compare(s)  # no explicit preference: the persona's
    assert set(res["data"]["routes"]) == {"fastest", "balanced", "sunniest"}
    assert res["data"]["preference"] == "sun" and "wellbeing" in res["data"]
    st = s.store
    assert st.resolve_path("route.sunniest.sun_gained_min").endswith(" min")
    assert st.get("route.sunniest.sun_gained_s") > 30
    assert st.resolve_path("wellbeing.uv.band") in ("low", "moderate", "high", "very high", "extreme")
    assert st.resolve_path("wellbeing.daylight_window.text")
    assert st.resolve_path("wellbeing.daylight_window.sun_alt_deg").endswith("°")
    assert s.plans[s.draft_plan_id]["preference"] == "sun"


def test_tourist_can_ask_for_sun_and_shade_stays_unchanged(sess):
    s = sess("tourist")
    shade = _compare(s)
    assert set(shade["data"]["routes"]) == {"fastest", "balanced", "coolest"}
    assert "wellbeing" not in shade["data"] and s.store.get("wellbeing") is None
    s2 = sess("tourist")
    sun = _compare(s2, preference="sun")
    assert "sunniest" in sun["data"]["routes"]
    bad, _ = tools.execute(
        sess("tourist"),
        "compare_routes",
        {"origin": "North East Tower", "dest": "Arcade Mall", "preference": "moon"},
    )
    assert not bad["ok"] and "preference" in bad["summary"]


def test_departure_and_plan_day_take_preference(sess):
    s = sess()
    _compare(s)
    dep, _ = tools.execute(
        s,
        "optimise_departure",
        {"origin": "origin", "dest": "dest", "window": {"start": "14:00", "end": "15:00"}},
    )
    assert dep["ok"] and s.store.get("departure.preference") == "sun"
    assert "shade_s" in s.store.get("departure.table")[0]
    day, _ = tools.execute(s, "plan_day", {"stops": ["North East Tower", "Arcade Mall"], "start": "14:30"})
    assert day["ok"], day


def test_scripted_daylight_seeker_turn(sess):
    s = sess()
    agent = Agent(s, ScriptedLLM(s, SPEC))
    ev = list(agent.run_turn(PROMPT))
    calls = [e["payload"] for e in ev if e["type"] == "tool_call"]
    assert any(c["name"] == "compare_routes" and c["args"].get("preference") == "sun" for c in calls)
    ver = next(e for e in ev if e["type"] == "verifier")["payload"]
    assert ver["defects"] == [], ver
    assert s.draft_plan()["recommendation"] == "sunniest"
    msg = ev[-1]["payload"]
    assert ev[-1]["type"] == "message" and "{{" not in msg["text"]
    assert "more daylight" in msg["text"] and "not medical advice" in msg["text"]
    assert "UV is" in msg["text"]
    assert find_violations(msg["template"], PROMPT) == []


def test_verifier_rejects_medical_claims_and_false_sun_claims(sess):
    s = sess()
    _compare(s)
    pid = s.draft_plan_id
    ok = verify_deterministic(
        s,
        Draft("Take the sunniest walk: {{route.sunniest.sun_gained_min}} more daylight.", pid, "sunniest"),
        PROMPT,
    )
    assert ok.passed, ok.defects
    med = verify_deterministic(
        s, Draft("This sunny walk treats vitamin D deficiency.", pid, "sunniest"), PROMPT
    )
    assert any("medical claim" in d for d in med.defects)
    s.plans[pid]["routes"]["sunniest"]["sun_gained_s"] = 0.0
    false_gain = verify_deterministic(
        s, Draft("The sunniest walk gives more daylight.", pid, "sunniest"), PROMPT
    )
    assert any("gains no sun" in d for d in false_gain.defects)


def test_planner_prompt_sun_rules():
    p = planner_prompt("daylight_seeker")
    assert "Daylight seeker" in p and 'preference "sun"' in p and "vitamin D" in p
    assert "not medical advice" in p and "sunniest" in p


# ---- the shipped scripted replay ---------------------------------------------------------------
def test_shipped_daylight_seeker_replay_matches_hero_sun():
    f = config.REPLAY_DIR / "daylight_seeker.json"
    rec = json.loads(f.read_text(encoding="utf-8"))
    assert rec["scenario_id"] == "daylight_seeker" and rec["persona"] == "daylight_seeker"
    assert rec["live"] is False and rec["model"] == "zill-scripted-planner"
    hero = json.loads((config.DATA_DIR / "scenarios" / "hero.json").read_text(encoding="utf-8"))
    sc = next(x for x in hero["sun"]["scenarios"] if x["id"] == "spring_daylight_walk")
    assert rec["date_id"] == sc["date_id"] and sc["depart"] in rec["prompt"]
    prop = next(i["event"]["payload"] for i in rec["events"] if i["event"]["type"] == "proposal")
    got = {r["label"]: r["stats"] for r in prop["routes"]}
    for label in ("fastest", "sunniest"):
        for k in ("duration_s", "sun_exposure_s"):
            assert got[label][k] == pytest.approx(sc[label]["stats"][k], abs=1.0)
    msg = [i["event"]["payload"] for i in rec["events"] if i["event"]["type"] == "message"][-1]
    assert "Daylight / vitamin D window" in msg["text"] and "not medical advice" in msg["text"]
    for bad in ("treat", "cure", "prevent"):
        assert bad not in msg["text"].lower()
    recs = replay.load_all()
    assert replay.match_intent("I want a sunny walk with more daylight", recs) == "daylight_seeker"
    assert replay.match_intent("I'm walking and it is so hot, find me some shade", recs) == "tourist_walk"

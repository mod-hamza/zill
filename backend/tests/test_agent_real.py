# ruff: noqa: E501
"""Agent on the REAL engine (routing, exposure, weather, departure optimiser) over the synthetic baked city."""

from __future__ import annotations

import pytest

from tests.synth_fixtures import synth_ctx, synth_env  # noqa: F401
from zill.agent.backend import BackendError, ServicesBackend
from zill.agent.orchestrator import Agent
from zill.agent.scripted import ScriptedLLM
from zill.agent.session import Session, SimClock
from zill.agent.tokens import find_violations

SPEC = {"persona": "tourist", "origin": "North West Plaza", "dest": "South East Hotel", "mode": "walk",
        "depart": "13:30", "flexible": True, "cool_stops": True}
PROMPT = "North West Plaza to South East Hotel, 13:30, I'm walking"


@pytest.fixture()
def real(synth_env, monkeypatch):  # noqa: F811
    monkeypatch.setenv("ZILL_WEATHER_LIVE", "0")
    be = ServicesBackend("synth")
    s = Session(persona="tourist", backend=be, date_key="summer", city="synth", autonomy=3)
    s.clock = SimClock(s.parse_time("13:30"), rate=0.0)
    return s, Agent(s, ScriptedLLM(s, SPEC))


def test_backend_resolve_and_validate(synth_env):  # noqa: F811
    be = ServicesBackend("synth")
    p = be.resolve_place("north west plaza")
    assert p["id"] == "nw_corner" and p["node"] == 0
    assert be.resolve_place("Arcade Mall")["kind"] == "mall"
    with pytest.raises(BackendError):
        be.resolve_place("Atlantis Lost City")
    routes = be.routes(p, be.resolve_place("South East Hotel"), "walk", be.ctx.at("summer", "13:30"), "summer",
                       {"fastest": 0.0, "coolest": 3.0})
    assert routes["fastest"]["stats"]["added_time_s"] == 0
    assert routes["coolest"]["sun_exposure_s"] <= routes["fastest"]["sun_exposure_s"] + 1e-6
    assert be.validate_route(routes["coolest"], "walk") == []


def test_full_turn_real_tools(real):
    s, agent = real
    ev = list(agent.run_turn(PROMPT))
    types = [e["type"] for e in ev]
    assert types[-1] == "message" and "error" not in types
    names = [e["payload"]["name"] for e in ev if e["type"] == "tool_call"]
    assert names[:4] == ["resolve_place", "resolve_place", "get_weather", "compare_routes"]
    assert all(e["payload"]["ok"] for e in ev if e["type"] == "tool_result"), [
        e["payload"]["summary"] for e in ev if e["type"] == "tool_result" and not e["payload"]["ok"]]
    v = next(e for e in ev if e["type"] == "verifier")["payload"]
    assert v["defects"] == []
    msg = ev[-1]["payload"]
    assert "{{" not in msg["text"] and find_violations(msg["template"], PROMPT) == []
    assert s.store.resolve_path("weather.source") in ("representative", "cached", "live")
    # numbers in the text are exactly the tool values
    r = s.plans[s.draft_plan_id]["routes"]["fastest"]
    assert s.store.resolve_path("route.fastest.duration_min") == f"{r['duration_s'] / 60:.1f} min"


def test_replan_after_delay_with_real_router(real):
    s, agent = real
    list(agent.run_turn(PROMPT))
    list(agent.approve(s.pending["plan_id"], True))
    ev = list(agent.monitor.simulate("delay", {"minutes": 20}))
    rp = next(e for e in ev if e["type"] == "replan")["payload"]
    assert rp["diff"]["delay_s"] == 1200 and rp["diff"]["blocked"] is False
    # same path at a later time has the same duration -> arrival differs from the delayed baseline by ~0
    assert abs(rp["diff"]["delta_arrival_s"]) < 5 or rp["diff"]["route_changed"]
    assert ev[-1]["type"] == "message"


def test_closure_uses_router_blocked_edges(real):
    s, agent = real
    list(agent.run_turn(PROMPT))
    list(agent.approve(s.pending["plan_id"], True))
    route = s.active_plan["routes"][s.active_plan["recommendation"]]
    edge = route["edges"][len(route["edges"]) // 2]
    ev = list(agent.monitor.simulate("closure", {"edge": edge}))
    rp = next(e for e in ev if e["type"] == "replan")["payload"]
    if not rp["diff"]["blocked"]:
        new_edges = s.plans[rp["new_plan_id"]]["routes"][s.plans[rp["new_plan_id"]]["recommendation"]]["edges"]
        assert edge not in new_edges

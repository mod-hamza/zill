# ruff: noqa: E501
"""Recorder, replay playback, intent matching, agent endpoints (live path via fake model, replay offline)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.agent_fakes import SyntheticBackend
from zill import config
from zill.agent import replay
from zill.agent.llm import ChatResult, FakeLLM, ToolCall
from zill.agent.tokens import find_violations
from zill.api import routes_agent
from zill.api.main import app

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("record_replay", ROOT / "scripts" / "record_replay.py")
rr = importlib.util.module_from_spec(SPEC)
sys.modules["record_replay"] = rr
SPEC.loader.exec_module(rr)

SC = {
    "tourist_walk": {"id": "tourist_walk", "persona": "tourist", "mode": "walk", "depart": "13:30", "date_id": "summer",
                     "origin": {"name": "metro"}, "dest": {"name": "Dubai Opera"}},
    "rider_cycle": {"id": "rider_cycle", "persona": "rider", "mode": "cycle", "depart": "13:30", "date_id": "summer",
                    "origin": {"name": "mall"}, "dest": {"name": "hotel"}},
    "crew_shuttle": {"id": "crew_shuttle", "persona": "crew", "mode": "walk", "depart": "13:30", "date_id": "summer",
                     "origin": {"name": "metro"}, "dest": {"name": "mall"}},
}


@pytest.fixture(scope="module")
def recordings(tmp_path_factory):
    out = tmp_path_factory.mktemp("replay")
    be = SyntheticBackend()
    for sid, sc in SC.items():
        rec = rr.record_scenario(be, sc, sid, live=False)
        (out / f"{sid}.json").write_text(json.dumps(rec), encoding="utf-8")
    rec = rr.record_scenario(be, SC["tourist_walk"], "replan_demo", live=False, autonomy=3, replan_minutes=20)
    (out / "replan_demo.json").write_text(json.dumps(rec), encoding="utf-8")
    return out


def assert_no_bare_numbers(rec: dict) -> int:
    """Every `message` text: after removing resolved token values, nothing numeric the user did not say."""
    n = 0
    for item in rec["events"]:
        ev = item["event"]
        if ev["type"] != "message":
            continue
        p = ev["payload"]
        assert "{{" not in p["text"], "unresolved token leaked"
        assert find_violations(p["template"], rec["prompt"]) == [], p["template"]
        rest = p["text"]
        for r in sorted(p["resolved"], key=lambda r: -len(r["value"])):
            rest = rest.replace(r["value"], " ")
        assert find_violations(rest, rec["prompt"]) == [], rest
        n += 1
    return n


def test_recorded_files_shape_and_no_bare_numbers(recordings):
    for sid in [*SC, "replan_demo"]:
        rec = json.loads((recordings / f"{sid}.json").read_text(encoding="utf-8"))
        assert rec["scenario_id"] == sid and rec["live"] is False and rec["model"] and rec["prompt"]
        assert rec["events"] and all({"dt_ms", "event", "phase"} <= set(i) for i in rec["events"])
        assert {"id", "ts", "type", "payload"} <= set(rec["events"][0]["event"])
        assert assert_no_bare_numbers(rec) >= 1
    rd = json.loads((recordings / "replan_demo.json").read_text(encoding="utf-8"))
    phases = [i["phase"] for i in rd["events"]]
    assert phases == sorted(phases, key={"plan": 0, "approve": 1, "monitor": 2}.get) and "monitor" in phases
    kinds = [i["event"]["type"] for i in rd["events"] if i["phase"] == "monitor"]
    assert "replan" in kinds and "plan_committed" in kinds  # auto-applied under L3


def test_shipped_recordings_if_present():
    """The real recordings in backend/replay (once recorded) must also be free of bare numbers."""
    files = sorted(config.REPLAY_DIR.glob("*.json"))
    if not files:
        pytest.skip("no recordings shipped yet")
    seen = set()
    for f in files:
        rec = json.loads(f.read_text(encoding="utf-8"))
        seen.add(rec["scenario_id"])
        assert rec["live"] in (True, False)
        assert_no_bare_numbers(rec)
    assert {"tourist_walk", "rider_cycle", "crew_shuttle", "replan_demo"} <= seen


def test_play_orders_events_scales_time_and_badges(recordings):
    recs = replay.load_all(recordings)
    slept: list[float] = []
    evs = list(replay.play(recs["tourist_walk"], "plan", speed=2.0, sleep=slept.append))
    assert [e["type"] for e in evs][0] == "session_started" and evs[-1]["type"] == "message"
    assert evs[-1]["payload"]["replay"]["source"] == "scripted"
    assert "Scripted session" in evs[-1]["payload"]["replay"]["label"]
    raw = [i["dt_ms"] / 1000 / 2.0 for i in recs["tourist_walk"]["events"] if i["phase"] == "plan" and i["dt_ms"] > 0]
    assert slept == pytest.approx([min(x, 2.5 / 2.0) for x in raw])
    ids = [e["id"] for e in evs]
    assert ids == sorted(ids)
    assert [e["type"] for e in replay.play(recs["tourist_walk"], "approve", sleep=lambda s: None)][0] == "plan_committed"
    recs["tourist_walk"]["live"] = True
    assert next(replay.play(recs["tourist_walk"], "plan", sleep=lambda s: None))["payload"]["replay"]["source"] == "recorded"


def test_intent_matching(recordings):
    recs = replay.load_all(recordings)
    intents = replay.load_intents()
    assert replay.match_intent(recs["tourist_walk"]["prompt"], recs, intents) == "tourist_walk"  # exact prompt
    assert replay.match_intent("I'm walking and it is so hot, find me some shade", recs, intents) == "tourist_walk"
    assert replay.match_intent("my courier bike delivery route please", recs, intents) == "rider_cycle"
    assert replay.match_intent("my crew shift midday work policy", recs, intents) == "crew_shuttle"
    assert replay.match_intent("what is the capital of France", recs, intents) is None
    assert replay.match_intent("", recs, intents) is None


def test_intents_file_covers_all_scenarios():
    ids = {i["scenario_id"] for i in replay.load_intents()}
    assert ids == {"tourist_walk", "rider_cycle", "crew_shuttle", "replan_demo"}


# ------------------------------------------------------------------ API
def parse_sse(text: str) -> list[dict]:
    out = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n") if ": " in line)
        assert lines["event"] == "agent"
        out.append(json.loads(lines["data"]))
    return out


@pytest.fixture()
def client(monkeypatch, recordings):
    monkeypatch.setattr(routes_agent, "REPLAY_DIR", recordings)
    monkeypatch.setattr(routes_agent, "BACKEND_FACTORY", lambda city: SyntheticBackend())
    routes_agent.reset_llm()
    routes_agent.SESSIONS.clear()
    yield TestClient(app)
    routes_agent.reset_llm()


def test_replay_endpoints_work_with_no_network_and_no_key(client, monkeypatch):
    monkeypatch.setattr(config, "REPLAY", True)
    monkeypatch.setattr(routes_agent, "LLM_FACTORY", lambda: (_ for _ in ()).throw(AssertionError("must not call LLM")))
    s = client.post("/api/agent/session", json={"persona": "tourist", "autonomy_level": 3}).json()
    assert s["mode"] == "replay" and s["badge"]["label"] == "Recorded session"
    r = client.get("/api/agent/replays").json()
    assert {x["scenario_id"] for x in r["replays"]} == {"tourist_walk", "rider_cycle", "crew_shuttle", "replan_demo"}
    assert all(x["badge"]["source"] == "scripted" and x["live"] is False for x in r["replays"])
    prompt = next(x["prompt"] for x in r["replays"] if x["scenario_id"] == "tourist_walk")
    res = client.post("/api/agent/message", json={"session_id": s["session_id"], "text": prompt, "speed": 0})
    assert res.headers["content-type"].startswith("text/event-stream")
    evs = parse_sse(res.text)
    assert evs[-1]["type"] == "message" and "approval_request" in [e["type"] for e in evs]
    ap = parse_sse(client.post("/api/agent/approve", json={"session_id": s["session_id"], "speed": 0}).text)
    assert ap[0]["type"] == "plan_committed"
    # unmatched free text
    un = parse_sse(client.post("/api/agent/message", json={"session_id": s["session_id"], "text": "capital of France?",
                                                          "speed": 0}).text)
    assert un[0]["payload"]["text"] == replay.UNMATCHED_TEXT
    # replan demo is replayed through the simulate endpoint
    client.post("/api/agent/message", json={"session_id": s["session_id"], "text": "I am late, please replan",
                                            "speed": 0})
    sim = parse_sse(client.post("/api/agent/simulate", json={"session_id": s["session_id"], "type": "delay",
                                                             "params": {"minutes": 20}, "speed": 0}).text)
    assert "replan" in [e["type"] for e in sim]


def test_unknown_session_404(client):
    assert client.post("/api/agent/message", json={"session_id": "nope", "text": "hi"}).status_code == 404


def tc(name, args, i):
    return ToolCall(id=f"c{i}", name=name, arguments=args)


def test_live_path_with_fake_openai_server(client, monkeypatch):
    """Live code path: available() true -> real orchestrator, real tools (synthetic engine), fake model."""
    monkeypatch.setattr(config, "REPLAY", False)
    verdict = json.dumps({"passed": True, "claims_checked": 4, "defects": []})
    draft = json.dumps({"plan_id": "plan_1", "recommendation": "coolest",
                        "text": "The coolest walk saves {{route.coolest.sun_saved_min}}."})
    script = [
        ChatResult(tool_calls=[tc("resolve_place", {"query": "metro", "role": "origin"}, 1),
                               tc("resolve_place", {"query": "opera", "role": "dest"}, 2)]),
        ChatResult(tool_calls=[tc("compare_routes", {"origin": "origin", "dest": "dest", "depart_at": "13:30"}, 3)]),
        draft, verdict, "Take the shaded walk; it saves {{route.coolest.sun_saved_min}}.",
    ]
    monkeypatch.setattr(routes_agent, "LLM_FACTORY", lambda: FakeLLM(script))
    s = client.post("/api/agent/session", json={"persona": "tourist", "autonomy_level": 2}).json()
    assert s["mode"] == "live"
    evs = parse_sse(client.post("/api/agent/message", json={"session_id": s["session_id"],
                                                            "text": "Metro to the Opera at 13:30"}).text)
    types = [e["type"] for e in evs]
    assert types[0] == "session_started" and types[-1] == "message"
    assert "verifier" in types and "approval_request" in types
    assert evs[-1]["payload"]["text"].startswith("Take the shaded walk; it saves ")
    appr = next(e for e in evs if e["type"] == "approval_request")["payload"]
    ap = parse_sse(client.post("/api/agent/approve", json={"session_id": s["session_id"], "plan_id": appr["plan_id"],
                                                           "approve": True}).text)
    assert ap[0]["type"] == "plan_committed"
    sim = parse_sse(client.post("/api/agent/simulate", json={"session_id": s["session_id"], "type": "delay",
                                                             "params": {"minutes": 20}}).text)
    assert "replan" in [e["type"] for e in sim]


def test_live_llm_error_streams_error_event_not_500(client, monkeypatch):
    monkeypatch.setattr(config, "REPLAY", False)
    monkeypatch.setattr(routes_agent, "LLM_FACTORY", lambda: FakeLLM([]))
    s = client.post("/api/agent/session", json={"persona": "rider"}).json()
    r = client.post("/api/agent/message", json={"session_id": s["session_id"], "text": "go"})
    assert r.status_code == 200 and parse_sse(r.text)[-1]["type"] == "error"


def test_unavailable_llm_falls_back_to_replay(client, monkeypatch):
    monkeypatch.setattr(config, "REPLAY", False)

    class Down(FakeLLM):
        def available(self) -> bool:
            return False

    monkeypatch.setattr(routes_agent, "LLM_FACTORY", lambda: Down())
    assert client.post("/api/agent/session", json={"persona": "tourist"}).json()["mode"] == "replay"


# ------------------------------------------------------------------ hero.json consistency, dates, health
HERO = config.DATA_DIR / "scenarios" / "hero.json"


def test_recordings_match_hero_json():
    """The first compare_routes in each shipped recording equals hero.json (same date, depart, graph)."""
    if not HERO.exists() or not any(config.REPLAY_DIR.glob("*.json")):
        pytest.skip("hero.json or recordings missing")
    hero = {s["id"]: s for s in json.loads(HERO.read_text(encoding="utf-8"))["scenarios"]}
    for sid in ("tourist_walk", "rider_cycle", "crew_shuttle"):
        rec = json.loads((config.REPLAY_DIR / f"{sid}.json").read_text(encoding="utf-8"))
        first = next(
            i["event"]["payload"]
            for i in rec["events"]
            if i["event"]["type"] == "tool_result" and i["event"]["payload"]["name"] == "compare_routes"
        )
        sc = hero[sid]
        assert rec["date_id"] == sc["date_id"]
        for label in ("fastest", "balanced", "coolest"):
            got, want = first["data"]["routes"][label], sc[label]["stats"]
            assert got["depart"] == sc[label]["depart"], (sid, label, "different date/departure than hero.json")
            for k in ("duration_s", "sun_exposure_s"):
                assert abs(got["stats"][k] - want[k]) <= 1.0, (sid, label, k, got["stats"][k], want[k])


def test_recorder_refuses_stale_hero_stats():
    sc = {**SC["tourist_walk"], "fastest": {"stats": {"duration_s": 1.0, "sun_exposure_s": 1.0}}}
    with pytest.raises(rr.HeroMismatch):
        rr.record_scenario(SyntheticBackend(), sc, "tourist_walk", live=False)


def test_bare_clock_times_resolve_against_session_date():
    from zill.agent.session import Session

    for key, day in (("summer", "2026-07-15"), ("winter", "2026-01-15"), ("hackathon", "2026-10-24")):
        s = Session(persona="tourist", backend=SyntheticBackend(), date_key=key)
        assert s.parse_time("14:30").isoformat() == f"{day}T14:30:00+04:00"
        from zill.agent import tools

        res, _ = tools.execute(s, "get_sun", {"at": "14:30"})
        assert res["data"]["at"].startswith(f"{day}T14:30")


def test_health_exposes_agent_status():
    h = TestClient(app).get("/api/health").json()["agent"]
    assert h["mode"] in ("live", "replay") and isinstance(h["recordings"], int)
    assert {"replay_available", "recordings_scripted", "recordings_live", "recording_kind"} <= set(h)
    if any(config.REPLAY_DIR.glob("*.json")):
        assert h["replay_available"] and h["recordings"] >= 4

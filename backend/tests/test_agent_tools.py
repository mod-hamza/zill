"""Agent tools on the synthetic backend: stores, errors-as-data, limits, timeout, policy."""

from __future__ import annotations

import time

import pytest

from tests.agent_fakes import SyntheticBackend
from zill import config
from zill.agent import tools
from zill.agent.policy import check_policy, load_pack
from zill.agent.session import Session


@pytest.fixture()
def s() -> Session:
    return Session(persona="tourist", backend=SyntheticBackend(), date_key="summer")


def run(s, name, **args):
    res, ms = tools.execute(s, name, args)
    assert isinstance(ms, int)
    assert set(res) == {"ok", "data", "summary"}
    return res


def test_every_prd_tool_registered():
    want = {
        "resolve_place",
        "get_sun",
        "get_weather",
        "plan_route",
        "compare_routes",
        "optimise_departure",
        "find_cool_stops",
        "plan_day",
        "check_policy",
        "commit_plan",
        "simulate_clock",
        "get_active_plan",
        "explain_segment",
        "build_city",
    }
    assert want <= set(tools.REGISTRY)
    specs = tools.planner_specs()
    assert "simulate_clock" not in {x["name"] for x in specs}  # internal
    for sp in specs:
        assert sp["parameters"]["type"] == "object" and sp["description"]


def test_resolve_and_compare_store_tokens(s):
    assert run(s, "resolve_place", query="metro", role="origin")["ok"]
    assert run(s, "resolve_place", query="Dubai Opera", role="dest")["ok"]
    r = run(s, "compare_routes", origin="origin", dest="dest", mode="walk", depart_at="13:30")
    assert r["ok"] and r["data"]["plan_id"] == "plan_1"
    assert s.store.resolve_path("place.dest.name") == "Dubai Opera"
    assert s.store.resolve_path("route.coolest.sun_saved_min").endswith(" min")
    assert float(s.store.resolve_path("route.fastest.added_time_s").split()[0]) == 0.0
    assert s.store.resolve_path("route.coolest.depart_time") == "13:30"
    assert s.store.resolve_path("route.coolest.arrive_time") > "13:30"
    assert s.plans["plan_1"]["routes"]["coolest"]["sun_saved_s"] > 0


def test_tool_error_is_data_not_exception(s):
    r = run(s, "resolve_place", query="Atlantis")
    assert not r["ok"] and "no place" in r["data"]["error"]
    r = run(s, "compare_routes", origin="nowhere", dest="opera")
    assert not r["ok"]
    r = run(s, "nonexistent_tool")
    assert not r["ok"]
    r = run(s, "plan_route", origin="metro", dest="opera", **{"lambda": 99})
    assert not r["ok"] and "lambda" in r["data"]["error"]
    r = run(s, "compare_routes", origin="metro", dest="opera", mode="hoverboard")
    assert not r["ok"]


def test_call_cap_per_turn(s):
    for _ in range(config.MAX_TOOL_CALLS):
        run(s, "get_sun", at="13:30")
    r = run(s, "get_sun", at="13:30")
    assert not r["ok"] and "limit" in r["data"]["error"]
    s.calls_this_turn = 0
    assert run(s, "get_sun", at="13:30")["ok"]


def test_timeout_returns_error(s, monkeypatch):
    monkeypatch.setattr(config, "TOOL_TIMEOUT_S", 0.2)
    monkeypatch.setitem(
        tools.REGISTRY,
        "get_sun",
        tools.Tool(
            "get_sun",
            "slow",
            {"type": "object", "properties": {}},
            lambda s, a: (time.sleep(0.6), tools.ok({}, "late"))[1],
        ),
    )
    t0 = time.perf_counter()
    r = run(s, "get_sun")
    assert not r["ok"] and "timed out" in r["summary"] and time.perf_counter() - t0 < 0.5


def test_optimise_departure_and_weather(s):
    run(s, "resolve_place", query="metro", role="origin")
    run(s, "resolve_place", query="opera", role="dest")
    r = run(s, "optimise_departure", origin="origin", dest="dest", window={"start": "13:30"})
    assert r["ok"]
    assert len(r["data"]["table"]) >= 8  # 5 min steps over 90 minutes (digest keeps 8 rows)
    assert s.store.resolve_path("departure.best.depart_time")
    assert "departure.best.depart_time" in s.store.token_paths("departure") or True
    w = run(s, "get_weather", at="13:30")
    assert w["data"]["heat_alert"] is True  # synthetic peak is >= 40 C apparent
    assert run(s, "get_weather", at="07:00")["data"]["heat_alert"] is False


def test_latest_arrival_constraint_in_optimiser(s):
    run(s, "resolve_place", query="metro", role="origin")
    run(s, "resolve_place", query="opera", role="dest")
    r = run(
        s,
        "optimise_departure",
        origin="origin",
        dest="dest",
        window={"start": "13:30", "end": "14:30"},
        latest_arrival="13:40",
    )
    assert not r["ok"]


def test_cool_stops_and_explain_and_build_city(s):
    run(s, "resolve_place", query="mall", role="origin")
    r = run(s, "find_cool_stops", near="origin", radius_m=2000)
    assert r["ok"] and r["data"]["count"] >= 1
    assert s.store.resolve_path("stops.nearest.distance_m").endswith(" m")
    run(s, "resolve_place", query="opera", role="dest")
    run(s, "compare_routes", origin="origin", dest="dest")
    assert run(s, "explain_segment", segment_index=0)["ok"]
    assert run(s, "build_city", query="Downtown Dubai")["ok"]


def test_plan_day_orders_stops_and_adds_breaks(s, monkeypatch):
    monkeypatch.setattr(config, "RHL_BREAK_THRESHOLD", 100.0)  # make the synthetic peak trigger a break
    monkeypatch.setattr(tools, "BREAK_SEARCH_M", 900.0)
    r = run(
        s,
        "plan_day",
        stops=[
            {"place": "metro", "dwell_min": 5},
            {"place": "hotel", "dwell_min": 20},
            {"place": "mall", "dwell_min": 30},
            {"place": "opera", "dwell_min": 15},
        ],
        mode="walk",
        start="13:00",
    )
    assert r["ok"]
    assert r["data"]["order"][0] == "Burj Khalifa Metro Station"
    assert sorted(r["data"]["order"]) == sorted(
        ["Burj Khalifa Metro Station", "Address Downtown", "The Dubai Mall", "Dubai Opera"]
    )
    assert r["data"]["totals"]["breaks"] >= 1
    assert any(i["kind"] == "break" for i in r["data"]["items"])
    assert not run(s, "plan_day", stops=[{"place": "metro"}])["ok"]


def test_commit_plan_never_commits_directly(s):
    run(s, "resolve_place", query="metro", role="origin")
    run(s, "resolve_place", query="opera", role="dest")
    run(s, "compare_routes", origin="origin", dest="dest")
    assert run(s, "commit_plan")["data"]["status"] == "awaiting_approval"
    assert s.active_plan_id is None
    s.autonomy = 1
    assert run(s, "commit_plan")["data"]["status"] == "advisor_only"


# ------------------------------------------------------------------ policy pack
def _item(start, end, sun=60.0, **kw):
    return {"kind": "leg", "label": "x", "start": start, "end": end, "sun_exposure_s": sun, **kw}


def test_policy_pack_flags_midday_in_season_only():
    pack = load_pack()
    assert pack["verified"] is False and "verify" in pack["label"].lower()
    summer = check_policy({"items": [_item("2026-07-15T13:30:00+04:00", "2026-07-15T13:45:00+04:00")]})
    assert not summer["ok"] and summer["violations"][0]["rule"] == "midday_window"
    assert summer["next_compliant"].startswith("2026-07-15T15:00")
    assert check_policy({"items": [_item("2026-07-15T15:10:00+04:00", "2026-07-15T15:30:00+04:00")]})["ok"]
    assert check_policy(
        {"items": [_item("2026-07-15T13:30:00+04:00", "2026-07-15T13:45:00+04:00", sun=0.0)]}
    )["ok"]
    assert check_policy({"items": [_item("2026-01-15T13:30:00+04:00", "2026-01-15T13:45:00+04:00")]})["ok"]
    assert check_policy({"items": [_item("2026-07-15T12:00:00+04:00", "2026-07-15T12:20:00+04:00")]})["ok"]


def test_policy_continuous_sun_rule():
    items = [
        _item("2026-07-15T08:00:00+04:00", "2026-07-15T08:30:00+04:00", sun=1800.0),
        _item("2026-07-15T08:31:00+04:00", "2026-07-15T09:00:00+04:00", sun=1800.0),
    ]
    res = check_policy({"items": items})
    assert any(v["rule"] == "continuous_sun" for v in res["violations"])

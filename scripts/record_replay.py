"""Record agent sessions for replay mode (PRD 17.1, CONTRACTS 7).

Runs the REAL orchestrator against the REAL tools for the three hero scenarios (data/scenarios/hero.json)
plus the proactive replan demo, and writes backend/replay/<scenario_id>.json.

  backend/.venv/Scripts/python scripts/record_replay.py            # scripted planner, live=false
  backend/.venv/Scripts/python scripts/record_replay.py --live     # real model (needs ZILL_LLM_API_KEY), live=true
  backend/.venv/Scripts/python scripts/record_replay.py --only daylight_seeker   # just the sun-mode session

The daylight_seeker session (sun mode) is recorded from hero.json["sun"] scenario SUN_SCENARIO_ID and checked
against its fastest / sunniest stats.

Without a key the scripted planner issues genuine tool calls (see zill/agent/scripted.py); the files carry
"live": false and the UI badges them "Scripted session (live model not connected)".
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from zill import config  # noqa: E402
from zill.agent.backend import ServicesBackend, ToolBackend  # noqa: E402
from zill.agent.llm import LLMClient  # noqa: E402
from zill.agent.orchestrator import Agent  # noqa: E402
from zill.agent.scripted import MODEL_NAME, ScriptedLLM  # noqa: E402
from zill.agent.session import Session, SimClock  # noqa: E402

HERO = config.DATA_DIR / "scenarios" / "hero.json"
INTENTS = config.DATA_DIR / "curated" / "intents.json"
SCENARIO_IDS = ("tourist_walk", "rider_cycle", "crew_shuttle")
SUN_SCENARIO_ID = "spring_daylight_walk"  # hero.json["sun"]: the scenario with an open daylight window
SUN_REPLAY_ID = "daylight_seeker"
# Natural-feeling minimum gaps (ms) for scripted sessions; live sessions keep their real timing.
PACING_MS = {
    "session_started": 200,
    "thought": 650,
    "tool_call": 350,
    "tool_result": 450,
    "verifier": 800,
    "proposal": 700,
    "approval_request": 400,
    "message": 900,
    "plan_committed": 500,
    "monitor_tick": 600,
    "replan": 900,
    "error": 300,
}


def prompt_for(sc: dict[str, Any]) -> str:
    o, d, t = sc["origin"]["name"], sc["dest"]["name"], sc["depart"]
    persona = sc["persona"]
    if persona == "rider":
        return f"I'm cycling a delivery from {o} to {d}, leaving at {t}. Keep me out of the sun where it is cheap to."
    if persona == "crew":
        return f"My crew needs to move from {o} to {d} at {t}. Check it against the midday work policy."
    if persona == "daylight_seeker":
        return f"I'd like a sunny walk from {o} to {d} at {t}. I want more daylight on the way."
    return f"{o} to {d}, {t}, I'm walking. I tire easily in the heat."


def spec_for(sc: dict[str, Any]) -> dict[str, Any]:
    persona = sc["persona"]
    return {
        "persona": persona,
        "origin": sc["origin"]["name"],
        "dest": sc["dest"]["name"],
        "mode": sc["mode"],
        "depart": sc["depart"],
        "flexible": persona in ("tourist", "rider"),
        "cool_stops": persona == "tourist",
        "window_min": 90,
        **({"preference": "sun"} if persona == "daylight_seeker" else {}),
    }


class Recorder:
    """Collects events with the time since the previous event."""

    def __init__(self, scripted: bool) -> None:
        self.scripted, self.items = scripted, []
        self._t = time.perf_counter()

    def add(self, events, phase: str) -> None:
        for ev in events:
            now = time.perf_counter()
            real = int((now - self._t) * 1000)
            dt = max(real, PACING_MS.get(ev["type"], 300)) if self.scripted else real
            self.items.append({"dt_ms": dt, "event": ev, "phase": phase})
            self._t = time.perf_counter()


class HeroMismatch(RuntimeError):
    """The recorded compare_routes stats disagree with hero.json (stale hero.json or wrong date/time)."""


class PinnedBackend:
    """Delegates to a backend but resolves the scenario's origin/destination to the exact hero.json places."""

    def __init__(self, inner: ToolBackend, sc: dict[str, Any]) -> None:
        self._inner = inner
        self._pins = {sc[k]["name"].lower(): sc[k] for k in ("origin", "dest") if "node" in sc.get(k, {})}

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def resolve_place(self, query: str, mode: str = "walk") -> dict[str, Any]:
        p = self._pins.get(query.strip().lower())
        if p is None:
            return self._inner.resolve_place(query, mode)
        return {**p, "id": p.get("id") or p["name"].lower().replace(" ", "_"), "kind": p.get("kind")}


def check_against_hero(s: Session, sc: dict[str, Any], tol_s: float = 1.0) -> None:
    """First compare_routes (store key `route`, at the scenario's date/depart) must equal hero.json stats."""
    got = s.store.get("route") or {}
    for label in ("fastest", "coolest", "sunniest"):
        want = (sc.get(label) or {}).get("stats")
        if not want or label not in got:
            continue
        for k in ("duration_s", "sun_exposure_s"):
            if abs(float(got[label][k]) - float(want[k])) > tol_s:
                raise HeroMismatch(
                    f"{sc['id']} {label}.{k}: recorded {got[label][k]} vs hero.json {want[k]} "
                    f"(date {sc.get('date_id')} depart {sc['depart']}); hero.json is probably stale - regenerate with "
                    "`python -m zill.routing.scenarios`"
                )


def make_session(backend: ToolBackend, sc: dict[str, Any], autonomy: int) -> Session:
    s = Session(
        persona=sc["persona"], backend=backend, date_key=sc.get("date_id", "summer"), autonomy=autonomy
    )
    s.clock = SimClock(s.parse_time(sc["depart"]), rate=0.0)  # frozen: the recording is deterministic
    return s


def record_scenario(
    backend: ToolBackend,
    sc: dict[str, Any],
    scenario_id: str,
    live: bool,
    llm_factory: Callable[[], Any] | None = None,
    autonomy: int = 2,
    replan_minutes: float | None = None,
) -> dict[str, Any]:
    backend = PinnedBackend(backend, sc)  # type: ignore[assignment]
    s = make_session(backend, sc, autonomy)
    prompt = prompt_for(sc)
    if replan_minutes is not None:
        prompt += " I may run late, so keep watching and re-plan for me on autopilot."
    llm = (llm_factory or LLMClient)() if live else ScriptedLLM(s, spec_for(sc))
    agent = Agent(s, llm)
    rec = Recorder(scripted=not live)
    rec.add(agent.run_turn(prompt), "plan")
    check_against_hero(s, sc)
    if s.pending:
        rec.add(agent.approve(s.pending["plan_id"], True), "approve")
    if replan_minutes is not None and s.active_plan is not None:
        rec.add(agent.monitor.simulate("delay", {"minutes": replan_minutes}), "monitor")
    return {
        "scenario_id": scenario_id,
        "persona": sc["persona"],
        "prompt": prompt,
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": (getattr(llm, "chosen_model", None) or llm.model) if live else MODEL_NAME,
        "live": bool(live),
        "autonomy_level": autonomy,
        "city": s.city,
        "date_id": s.date_key,
        "pacing": "scripted-minimum" if not live else "real",
        "events": rec.items,
    }


def load_scenarios(wait_min: float) -> tuple[list[dict[str, Any]], str]:
    deadline = time.monotonic() + wait_min * 60
    while not HERO.exists() and time.monotonic() < deadline:
        print(f"waiting for {HERO} ...", flush=True)
        time.sleep(120)
    if HERO.exists():
        data = json.loads(HERO.read_text(encoding="utf-8"))
        by_id = {sc["id"]: sc for sc in data["scenarios"]}
        return [by_id[i] for i in SCENARIO_IDS if i in by_id], "hero.json"
    return fallback_scenarios(), "fallback (two POIs from pois.json; hero.json absent)"


def fallback_scenarios() -> list[dict[str, Any]]:
    from zill import services

    ctx = services.get_city(config.DEFAULT_CITY)
    pois = [p for p in ctx.pois if p.get("kind") in ("landmark", "mall", "metro", "hotel")][:4]
    if len(pois) < 2:
        raise SystemExit("no hero.json and fewer than two usable POIs; cannot record")
    a, b = pois[0], pois[1]

    def sc(i: str, persona: str, mode: str) -> dict[str, Any]:
        return {
            "id": i,
            "persona": persona,
            "mode": mode,
            "origin": {"name": a["name"]},
            "dest": {"name": b["name"]},
            "date_id": "summer",
            "depart": "13:30",
        }

    return [
        sc("tourist_walk", "tourist", "walk"),
        sc("rider_cycle", "rider", "cycle"),
        sc("crew_shuttle", "crew", "walk"),
    ]


def update_intents(recs: list[dict[str, Any]], scenarios: dict[str, dict[str, Any]]) -> None:
    data = json.loads(INTENTS.read_text(encoding="utf-8"))
    for it in data["intents"]:
        sc = scenarios.get(it["scenario_id"]) or (
            scenarios.get("tourist_walk") if it["scenario_id"] == "replan_demo" else None
        )
        if not sc:
            continue
        for name in (sc["origin"]["name"], sc["dest"]["name"]):
            if name not in it["keywords"]:
                it["keywords"].append(name)
    INTENTS.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sun_scenario() -> dict[str, Any] | None:
    """hero.json["sun"] scenario used for the daylight-seeker session (persona set to daylight_seeker)."""
    if not HERO.exists():
        return None
    sun = json.loads(HERO.read_text(encoding="utf-8")).get("sun") or {}
    sc = next((x for x in sun.get("scenarios", []) if x["id"] == SUN_SCENARIO_ID), None)
    return None if sc is None else {**sc, "persona": "daylight_seeker"}


def record_sun_only(a: argparse.Namespace) -> int:
    sc = sun_scenario()
    if sc is None:
        print(f"hero.json has no sun scenario {SUN_SCENARIO_ID}; run: python -m zill.routing.scenarios --sun")
        return 2
    backend = ServicesBackend(config.DEFAULT_CITY)
    backend.warm(block=True)
    try:
        rec = record_scenario(backend, sc, SUN_REPLAY_ID, a.live)
    except HeroMismatch as exc:
        print(f"ABORT (nothing written): {exc}", file=sys.stderr)
        return 3
    rec["source"] = f"hero.json sun/{SUN_SCENARIO_ID}"
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{SUN_REPLAY_ID}.json").write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    update_intents([rec], {SUN_REPLAY_ID: sc})
    print(f"recorded {SUN_REPLAY_ID}: {len(rec['events'])} events, live={rec['live']}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="use the real model (needs a key) -> live=true")
    ap.add_argument("--out", default=str(config.REPLAY_DIR))
    ap.add_argument("--wait-min", type=float, default=0.0, help="poll for hero.json up to N minutes")
    ap.add_argument("--delay-min", type=float, default=20.0)
    ap.add_argument("--only", choices=[SUN_REPLAY_ID], help="record only this session")
    a = ap.parse_args()
    if a.live:
        client = LLMClient()
        if not client.available():
            print(f"live model not available ({client.reason}); refusing to record --live", file=sys.stderr)
            return 2
    if a.only == SUN_REPLAY_ID:
        return record_sun_only(a)
    scenarios, source = load_scenarios(a.wait_min)
    print(f"scenarios from: {source}")
    backend = ServicesBackend(config.DEFAULT_CITY)
    backend.warm(block=True)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    by_id = {sc["id"]: sc for sc in scenarios}
    written: list[dict[str, Any]] = []
    try:
        for sc in scenarios:
            rec = record_scenario(backend, sc, sc["id"], a.live)
            rec["source"] = source
            written.append(rec)
            print(f"recorded {sc['id']}: {len(rec['events'])} events, live={rec['live']}")
        tourist = by_id.get("tourist_walk") or scenarios[0]
        rec = record_scenario(backend, tourist, "replan_demo", a.live, autonomy=3, replan_minutes=a.delay_min)
        rec["source"] = source
        written.append(rec)
        print(f"recorded replan_demo: {len(rec['events'])} events")
    except HeroMismatch as exc:
        print(f"ABORT (nothing written): {exc}", file=sys.stderr)
        return 3
    for rec in written:  # all-or-nothing: files are written only after every scenario recorded and checked
        (out / f"{rec['scenario_id']}.json").write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    update_intents(written, by_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

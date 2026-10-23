"""Agent endpoints (PRD 10, 11.3, 17.1): session / message (SSE) / approve / simulate / replays.

Live mode needs `llm.available()` and not ZILL_REPLAY; otherwise the closest recorded session is
replayed (badged "Recorded session" or "Scripted session (live model not connected)").
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from zill import config
from zill.agent import replay as replay_mod
from zill.agent.backend import ServicesBackend, ToolBackend
from zill.agent.llm import LLMClient
from zill.agent.orchestrator import Agent
from zill.agent.session import Session
from zill.api.sse import sse_event, sse_response

router = APIRouter(prefix="/api/agent", tags=["agent"])

# Test / deployment seams -------------------------------------------------------------------------
LLM_FACTORY: Callable[[], Any] = LLMClient
BACKEND_FACTORY: Callable[[str], ToolBackend] = lambda city: ServicesBackend(city)  # noqa: E731
REPLAY_DIR = None  # None -> config.REPLAY_DIR

_llm: Any = None
_lock = threading.Lock()
SESSIONS: dict[str, SessionState] = {}


class SessionState:
    def __init__(self, session: Session, agent: Agent | None, live: bool) -> None:
        self.session, self.agent, self.live = session, agent, live
        self.replay_scenario: str | None = None


def _session_llm(session_id: str) -> Any:
    """Per-conversation view of the LLM chain (OpenCode wants a stable session header)."""
    llm = get_llm()
    view = getattr(llm, "for_session", None)
    return view(session_id) if callable(view) else llm


def get_llm() -> Any:
    global _llm
    with _lock:
        if _llm is None:
            _llm = LLM_FACTORY()
        return _llm


def reset_llm() -> None:
    global _llm
    _llm = None


def live_available() -> bool:
    if config.REPLAY:
        return False
    try:
        return bool(get_llm().available())
    except Exception:
        return False


# Models --------------------------------------------------------------------------------------------
class SessionIn(BaseModel):
    persona: Literal["tourist", "rider", "crew"] = "tourist"
    city: str = config.DEFAULT_CITY
    date_id: str = "summer"
    clock: str | None = Field(default=None, description="HH:MM or ISO start of the simulated clock")
    autonomy_level: int = Field(default=2, ge=1, le=3)


class MessageIn(BaseModel):
    session_id: str
    text: str = Field(min_length=1, max_length=2000)
    speed: float = Field(default=1.0, ge=0.0, le=20.0)


class ApproveIn(BaseModel):
    session_id: str
    plan_id: str | None = None
    approve: bool = True
    undo_token: str | None = None
    speed: float = 1.0


class SimulateIn(BaseModel):
    session_id: str
    type: Literal["delay", "closure", "heat_alert", "sun_clock_jump", "tick"]
    params: dict[str, Any] = Field(default_factory=dict)
    speed: float = 1.0


def _state(sid: str) -> SessionState:
    st = SESSIONS.get(sid)
    if st is None:
        raise HTTPException(
            404, detail={"error": "unknown_session", "message": "Unknown or expired session."}
        )
    return st


def _stream(events: Iterator[dict[str, Any]]) -> Any:
    def gen() -> Iterator[str]:
        try:
            for ev in events:
                yield sse_event("agent", ev)
        except Exception as exc:  # never leak a stack trace to the client
            yield sse_event(
                "agent",
                {
                    "id": "evt_err",
                    "ts": "",
                    "type": "error",
                    "payload": {
                        "message": "The agent hit an unexpected error.",
                        "detail": type(exc).__name__,
                        "recoverable": True,
                    },
                },
            )

    return sse_response(gen())


# Endpoints -----------------------------------------------------------------------------------------
class ReplaySession:
    """Lightweight session used when the live agent is unavailable (no engine access needed)."""

    def __init__(self, body: SessionIn) -> None:
        import uuid

        self.id = "r_" + uuid.uuid4().hex[:10]
        self.persona, self.city, self.date_key, self.autonomy = (
            body.persona,
            body.city,
            body.date_id,
            body.autonomy_level,
        )
        self.clock_start = body.clock

    def public(self) -> dict[str, Any]:
        return {
            "session_id": self.id,
            "persona": self.persona,
            "city": self.city,
            "date_key": self.date_key,
            "autonomy_level": self.autonomy,
            "sim_time": self.clock_start,
            "active_plan_id": None,
        }


@router.post("/session")
def create_session(body: SessionIn) -> dict[str, Any]:
    live = live_available()
    if not live:
        rs = ReplaySession(body)
        SESSIONS[rs.id] = SessionState(rs, None, False)  # type: ignore[arg-type]
        return {
            **rs.public(),
            "mode": "replay",
            "llm": {"available": False},
            "badge": {"source": "recorded", "label": "Recorded session"},
        }
    try:
        backend = BACKEND_FACTORY(body.city)
        if hasattr(backend, "warm"):
            backend.warm()
        s = Session(
            persona=body.persona,
            backend=backend,
            date_key=body.date_id,
            city=body.city,
            autonomy=body.autonomy_level,
        )
        if body.clock:
            s.clock.jump(s.parse_time(body.clock))
    except Exception as exc:
        raise HTTPException(
            400, detail={"error": "bad_session", "message": f"Cannot start session: {exc}"}
        ) from exc
    SESSIONS[s.id] = SessionState(s, Agent(s, _session_llm(s.id)), True)
    return {**s.public(), "mode": "live", "llm": get_llm().status()}


@router.post("/message")
def post_message(body: MessageIn) -> Any:
    st = _state(body.session_id)
    if st.live and st.agent is not None:
        return _stream(st.agent.run_turn(body.text))
    recs = replay_mod.load_all(REPLAY_DIR)
    sid = replay_mod.match_intent(body.text, recs, persona=st.session.persona)
    st.replay_scenario = sid

    def events() -> Iterator[dict[str, Any]]:
        if sid is None:
            yield replay_mod.unmatched_event()
            return
        yield from replay_mod.play(recs[sid], "plan", body.speed)

    return _stream(events())


@router.post("/approve")
def post_approve(body: ApproveIn) -> Any:
    st = _state(body.session_id)
    if st.live and st.agent is not None:
        return _stream(st.agent.approve(body.plan_id, body.approve, body.undo_token))
    recs = replay_mod.load_all(REPLAY_DIR)

    def events() -> Iterator[dict[str, Any]]:
        if st.replay_scenario and st.replay_scenario in recs and body.approve and not body.undo_token:
            yield from replay_mod.play(recs[st.replay_scenario], "approve", body.speed)
        else:
            yield replay_mod.unmatched_event()

    return _stream(events())


@router.post("/simulate")
def post_simulate(body: SimulateIn) -> Any:
    st = _state(body.session_id)
    if st.live and st.agent is not None:
        return _stream(st.agent.monitor.simulate(body.type, body.params))
    recs = replay_mod.load_all(REPLAY_DIR)

    def events() -> Iterator[dict[str, Any]]:
        sid = (
            st.replay_scenario
            if st.replay_scenario in recs
            else ("replan_demo" if "replan_demo" in recs else None)
        )
        if sid and any(e.get("phase") == "monitor" for e in recs[sid]["events"]):
            yield from replay_mod.play(recs[sid], "monitor", body.speed)
        else:
            yield replay_mod.unmatched_event()

    return _stream(events())


@router.get("/replays")
def get_replays() -> dict[str, Any]:
    return {"replays": replay_mod.list_replays(REPLAY_DIR), "live_available": live_available()}


@router.get("/status")
def get_status() -> dict[str, Any]:
    llm = get_llm()
    st = llm.status() if not config.REPLAY else {"available": False, "reason": "ZILL_REPLAY=1"}
    return {"mode": "live" if live_available() else "replay", "llm": st}

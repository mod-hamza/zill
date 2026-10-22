"""Replay mode (PRD 17.1): play recorded agent sessions at natural pacing, never pretending to be live.

Recording format (CONTRACTS 7): backend/replay/<scenario_id>.json =
{"scenario_id","persona","prompt","recorded_at","model","live", "events":[{"dt_ms","event","phase"}]}
`phase` (extension, see CONTRACTS note) is "plan" | "approve" | "monitor" so the UI can step through
the same session: message -> approve -> simulate.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from zill import config

INTENTS_PATH = config.DATA_DIR / "curated" / "intents.json"
UNMATCHED_TEXT = "This is a recorded session. Connect to the network to chat live."
MIN_SCORE = 2

_WORD = re.compile(r"[a-z0-9]+")


def _words(s: str) -> set[str]:
    return set(_WORD.findall((s or "").lower()))


def load_all(directory: Path | None = None) -> dict[str, dict[str, Any]]:
    d = directory or config.REPLAY_DIR
    out: dict[str, dict[str, Any]] = {}
    if not d.is_dir():
        return out
    for f in sorted(d.glob("*.json")):
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(rec, dict) and rec.get("scenario_id") and isinstance(rec.get("events"), list):
            out[rec["scenario_id"]] = rec
    return out


def badge(rec: dict[str, Any]) -> dict[str, Any]:
    live = bool(rec.get("live"))
    return {
        "source": "recorded" if live else "scripted",
        "label": "Recorded session" if live else "Scripted session (live model not connected)",
    }


def list_replays(directory: Path | None = None) -> list[dict[str, Any]]:
    return [
        {
            "scenario_id": r["scenario_id"],
            "persona": r.get("persona"),
            "prompt": r.get("prompt"),
            "recorded_at": r.get("recorded_at"),
            "model": r.get("model"),
            "live": bool(r.get("live")),
            "events": len(r["events"]),
            "phases": sorted({e.get("phase", "plan") for e in r["events"]}),
            "badge": badge(r),
        }
        for r in load_all(directory).values()
    ]


def load_intents(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or INTENTS_PATH
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8")).get("intents", [])


def match_intent(
    text: str,
    recordings: dict[str, dict[str, Any]] | None = None,
    intents: list[dict[str, Any]] | None = None,
    persona: str | None = None,
) -> str | None:
    """Exact recorded prompt first, else keyword score over the intent table (>= MIN_SCORE hits)."""
    recs = recordings if recordings is not None else load_all()
    norm = " ".join(_WORD.findall((text or "").lower()))
    for sid, r in recs.items():
        if norm and norm == " ".join(_WORD.findall((r.get("prompt") or "").lower())):
            return sid
    words = _words(text)
    best, best_score = None, 0
    for it in intents if intents is not None else load_intents():
        sid = it["scenario_id"]
        if sid not in recs:
            continue
        hits = sum(1 for k in it.get("keywords", []) if (set(_WORD.findall(k.lower())) <= words))
        if persona and recs[sid].get("persona") == persona:
            hits += 0.5
        if hits > best_score:
            best, best_score = sid, hits
    return best if best_score >= MIN_SCORE else None


def play(
    rec: dict[str, Any],
    phase: str = "plan",
    speed: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
    max_dt_ms: int = 2500,
) -> Iterator[dict[str, Any]]:
    """Yield the recorded events of one phase with original relative timing (scaled by `speed`)."""
    b = badge(rec)
    for item in rec["events"]:
        if item.get("phase", "plan") != phase:
            continue
        dt = min(int(item.get("dt_ms", 0)), max_dt_ms) / 1000.0
        if speed > 0 and dt > 0:
            sleep(dt / speed)
        ev = json.loads(json.dumps(item["event"]))  # deep copy
        ev["ts"] = datetime.now(UTC).isoformat(timespec="milliseconds")
        ev.setdefault("payload", {})["replay"] = {**b, "scenario_id": rec["scenario_id"], "phase": phase}
        yield ev


def unmatched_event() -> dict[str, Any]:
    return {
        "id": "evt_replay_unmatched",
        "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
        "type": "message",
        "payload": {
            "text": UNMATCHED_TEXT,
            "resolved": [],
            "template": "",
            "source": "replay",
            "replay": {"source": "recorded", "label": "Recorded session"},
        },
    }

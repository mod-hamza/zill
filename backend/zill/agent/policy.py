"""Policy packs (PRD 11.7). Local fallback implementation of `check_policy`.

The UAE_OUTDOOR_WORK pack is data (`data/curated/policy_packs/*.json`), marked `verified: false`.
Never legal advice. If the ROUTING stream ships `zill.routing.policy.check_policy`, `check_policy`
here delegates to it first.
"""

from __future__ import annotations

import json
from datetime import datetime, time, timedelta
from functools import lru_cache
from typing import Any

from zill import config

PACK_DIR = config.DATA_DIR / "curated" / "policy_packs"

_DEFAULT_PACK: dict[str, Any] = {
    "id": "UAE_OUTDOOR_WORK",
    "label": "Policy pack: UAE midday break (v1, verify)",
    "verified": False,
    "midday_window": {"start": "12:30", "end": "15:00", "from_month_day": "06-15", "to_month_day": "09-15"},
    "max_continuous_sun_min": 45,
    "min_break_min": 10,
}


@lru_cache(maxsize=8)
def load_pack(pack_id: str = "UAE_OUTDOOR_WORK") -> dict[str, Any]:
    f = PACK_DIR / f"{pack_id.lower()}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    if pack_id == "UAE_OUTDOOR_WORK":
        return dict(_DEFAULT_PACK)
    raise KeyError(f"unknown policy pack '{pack_id}'")


def _hm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def in_season(dt: datetime, pack: dict[str, Any]) -> bool:
    w = pack["midday_window"]
    md = dt.strftime("%m-%d")
    return w["from_month_day"] <= md <= w["to_month_day"]


def midday_bounds(dt: datetime, pack: dict[str, Any]) -> tuple[datetime, datetime]:
    w = pack["midday_window"]
    return (
        datetime.combine(dt.date(), _hm(w["start"]), tzinfo=dt.tzinfo),
        datetime.combine(dt.date(), _hm(w["end"]), tzinfo=dt.tzinfo),
    )


def next_compliant_time(dt: datetime, pack: dict[str, Any]) -> datetime:
    """Earliest time at/after `dt` outside the midday window (same day)."""
    if not in_season(dt, pack):
        return dt
    start, end = midday_bounds(dt, pack)
    return end if start <= dt < end else dt


def _items(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Plan intervals to check: {kind, label, start, end, sun_s}."""
    out: list[dict[str, Any]] = []
    tz = None
    for it in plan.get("items", []):
        start = datetime.fromisoformat(it["start"])
        end = datetime.fromisoformat(it["end"])
        tz = tz or start.tzinfo
        out.append(
            {
                "kind": it.get("kind", "leg"),
                "label": it.get("label", ""),
                "start": start,
                "end": end,
                "sun_s": float(it.get("sun_exposure_s", it.get("sun_s", 0.0)) or 0.0),
                "outdoor_work": bool(it.get("outdoor_work", it.get("kind") in ("work", "leg"))),
            }
        )
    return out


def check_policy(plan: dict[str, Any], pack_id: str = "UAE_OUTDOOR_WORK") -> dict[str, Any]:
    """Return {pack, label, verified, ok, violations[], count, next_compliant_time}.

    `plan["items"]` is a list of timed intervals (route legs and work blocks) with `sun_exposure_s`.
    A violation is an outdoor interval with direct sun overlapping the midday window in season, or
    a continuous sun run longer than `max_continuous_sun_min`.
    """
    try:
        from zill.routing import policy as routing_policy  # type: ignore[attr-defined]

        if hasattr(routing_policy, "check_policy"):
            return routing_policy.check_policy(plan, pack_id)
    except ImportError:
        pass

    pack = load_pack(pack_id)
    violations: list[dict[str, Any]] = []
    items = _items(plan)
    nxt: datetime | None = None
    for it in items:
        if not it["outdoor_work"] or it["sun_s"] <= 0:
            continue
        if not in_season(it["start"], pack):
            continue
        w_start, w_end = midday_bounds(it["start"], pack)
        if it["start"] < w_end and it["end"] > w_start:
            overlap_s = (min(it["end"], w_end) - max(it["start"], w_start)).total_seconds()
            violations.append(
                {
                    "rule": "midday_window",
                    "item": it["label"],
                    "start": it["start"].isoformat(),
                    "overlap_s": overlap_s,
                    "overlap_min": overlap_s / 60.0,
                }
            )
            nxt = max(nxt, w_end) if nxt else w_end
    # continuous sun run
    limit = float(pack.get("max_continuous_sun_min", 45)) * 60.0
    run, prev_end = 0.0, None
    for it in sorted(items, key=lambda i: i["start"]):
        if it["sun_s"] <= 0 or not it["outdoor_work"]:
            run, prev_end = 0.0, it["end"]
            continue
        if prev_end is not None and (it["start"] - prev_end) > timedelta(
            minutes=pack.get("min_break_min", 10)
        ):
            run = 0.0
        run += it["sun_s"]
        prev_end = it["end"]
        if run > limit:
            violations.append(
                {"rule": "continuous_sun", "item": it["label"], "run_s": run, "run_min": run / 60}
            )
            run = 0.0
    return {
        "pack": pack["id"],
        "label": pack["label"],
        "verified": bool(pack.get("verified", False)),
        "ok": not violations,
        "violations": violations,
        "count": len(violations),
        "next_compliant": nxt.isoformat() if nxt else None,
        "midday_window_start": pack["midday_window"]["start"],
        "midday_window_end": pack["midday_window"]["end"],
    }

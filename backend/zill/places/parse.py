"""One-line trip parsing: "from X to Y at 15:30, cycle, sunny" (English and Arabic) -> places + options."""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from zill.places.fold import _AR_DIGITS, fold

AMBIGUOUS_BELOW = 85.0
AMBIGUOUS_GAP = 6.0
CANDIDATES = 5

MODE_WORDS = {
    "walk": "walk", "walking": "walk", "foot": "walk", "on foot": "walk", "مشي": "walk", "مشيا": "walk",
    "cycle": "cycle", "cycling": "cycle", "bike": "cycle", "biking": "cycle", "bicycle": "cycle",
    "دراجة": "cycle", "scooter": "scooter", "e-scooter": "scooter", "escooter": "scooter",
    "سكوتر": "scooter",
}  # fmt: skip
PREF_WORDS = {
    "shade": "shade", "shady": "shade", "shaded": "shade", "coolest": "shade", "cool": "shade",
    "shadiest": "shade", "ظل": "shade", "sun": "sun", "sunny": "sun", "sunniest": "sun", "sunlit": "sun",
    "sunlight": "sun", "daylight": "sun", "شمس": "sun", "مشمس": "sun",
}  # fmt: skip
FILLER = {"route", "path", "way", "the", "in", "a", "please", "with", "and", "mode", "trip", "ال"}

_SEP = re.compile(r"\s(?:to|till|until|الى|إلى|إلي|->|=>|→|>|-|–|—)\s|→|->|=>", re.I)
_FROM = re.compile(r"^\s*(?:from|من)\s+", re.I)
_AR_FROM_TO = re.compile(r"^\s*من\s+(.+?)\s+(?:إلى|الى|إلي)\s+(.+?)\s*$")
_BY = re.compile(r"\b(?:by|on|via|using)\s+(foot|bike|bicycle|scooter|e-scooter|escooter)\b", re.I)
_TIME_HM = re.compile(r"(?:\b(?:at|around|by|@)\s*)?\b(\d{1,2})(?::|h)(\d{2})\s*(am|pm)?\b", re.I)
_TIME_AMPM = re.compile(r"(?:\b(?:at|around|by|@)\s*)?\b(\d{1,2})(?:\.(\d{2}))?\s*(am|pm)\b", re.I)
_TIME_AT = re.compile(r"\bat\s+(\d{1,2})\b(?!\s*(?:st|nd|rd|th)\b)", re.I)
_TIME_AR = re.compile(r"الساعة\s*(\d{1,2})(?::(\d{2}))?")
_NOON = re.compile(r"\b(?:at\s+)?(noon|midday)\b", re.I)
_DAY = re.compile(r"\b(tomorrow|today|tonight)\b|(غدا|غدًا|بكرة|اليوم)", re.I)


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip(" \t,;.:!?؟،")


def _extract_time(t: str, now: datetime) -> tuple[str, str | None, str | None, str | None]:
    """Return (text without time/day words, 'HH:MM' or None, ISO date or None, ISO datetime or None)."""
    day_off: int | None = None
    m = _DAY.search(t)
    if m:
        w = (m.group(1) or m.group(2) or "").lower()
        day_off = 1 if w in ("tomorrow", "غدا", "غدًا", "بكرة") else 0
        t = t[: m.start()] + " " + t[m.end() :]
    hh = mm = None
    for rx in (_TIME_HM, _TIME_AMPM, _TIME_AR, _TIME_AT, _NOON):
        m = rx.search(t)
        if not m:
            continue
        if rx is _NOON:
            hh, mm = 12, 0
        else:
            hh = int(m.group(1))
            mm = int(m.group(2)) if m.lastindex and m.lastindex >= 2 and m.group(2) else 0
            ap = (m.group(3) if rx in (_TIME_HM, _TIME_AMPM) else None) or ""
            if ap.lower() == "pm" and hh < 12:
                hh += 12
            elif ap.lower() == "am" and hh == 12:
                hh = 0
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            hh = mm = None
            continue
        t = t[: m.start()] + " " + t[m.end() :]
        break
    hhmm = f"{hh:02d}:{mm:02d}" if hh is not None else None
    date_iso = iso = None
    if day_off is not None or hhmm:
        d = (now + timedelta(days=day_off or 0)).date()
        date_iso = d.isoformat()
        if hhmm:
            iso = datetime(d.year, d.month, d.day, hh, mm, tzinfo=now.tzinfo).isoformat()
    return _clean(t), hhmm, date_iso, iso


def _extract_options(t: str) -> tuple[str, str | None, str | None]:
    """Strip mode / preference words ("by bike", edge words like "sunny walk"); -> (text, mode, pref)."""
    mode = pref = None
    m = _BY.search(t)
    if m:
        mode = MODE_WORDS.get(m.group(1).lower())
        t = t[: m.start()] + " " + t[m.end() :]
    t = _clean(t)
    changed = True
    while changed and t:
        changed = False
        words = t.split(" ")
        for side in ("lead", "trail"):
            if not words:
                break
            w = (words[0] if side == "lead" else words[-1]).lower().strip(",.;")
            if side == "lead" and w in ("from", "من"):
                continue
            if w in MODE_WORDS:
                mode = mode or MODE_WORDS[w]
            elif w in PREF_WORDS:
                pref = pref or PREF_WORDS[w]
            elif w in FILLER and len(words) > 2 and (side == "trail" or words[0] != "from"):
                pass
            else:
                continue
            words = words[1:] if side == "lead" else words[:-1]
            changed = True
        t = _clean(" ".join(words))
    # a dangling filler/preposition at the end ("... in the", "... by")
    t = re.sub(r"\s+(?:in|by|on|via|with|the|a)$", "", t, flags=re.I)
    return t, mode, pref


def _splits(t: str) -> list[tuple[str, str]]:
    m = _AR_FROM_TO.match(t)
    if m:
        return [(m.group(1), m.group(2))]
    body = _FROM.sub("", t)
    out = []
    for m in _SEP.finditer(body):
        a, b = _clean(body[: m.start()]), _clean(body[m.end() :])
        if a and b:
            out.append((a, b))
    return out


def _far(a: dict[str, Any], b: dict[str, Any], metres: float = 150.0) -> bool:
    dy = (a["lat"] - b["lat"]) * 110574.0
    dx = (a["lon"] - b["lon"]) * 111320.0 * math.cos(math.radians(a["lat"]))
    return math.hypot(dx, dy) > metres


def _is_exact(text: str, p: dict[str, Any]) -> bool:
    f = fold(text)
    return f in (fold(p["name"]), fold(p.get("matched", "")), *[fold(a) for a in p.get("alt_names", [])])


def _side(city_id: str, text: str, searcher: Any, limit: int) -> dict[str, Any]:
    cands = searcher(city_id, text, limit)
    best = cands[0] if cands else None
    ambiguous = best is None or best["score"] < AMBIGUOUS_BELOW
    if best and len(cands) > 1 and not ambiguous:
        others = [c for c in cands[1:] if c["id"] != best["id"]]
        if _is_exact(text, best):
            # an exact name only stays ambiguous when another exact-named place is elsewhere (many branches)
            ambiguous = any(_is_exact(text, c) and _far(best, c) for c in others)
        else:
            ambiguous = any(
                c["name"] != best["name"] and best["score"] - c["score"] < AMBIGUOUS_GAP for c in others
            )
    conf = 0.0 if best is None else min(best["score"] / 100.0, 1.0) - (0.15 if ambiguous else 0.0)
    return {
        "text": text,
        "best": best,
        "candidates": cands,
        "ambiguous": ambiguous,
        "confidence": max(conf, 0),
    }


def parse_text(
    city_id: str,
    text: str,
    now: datetime | None = None,
    tz: str | None = None,
    searcher: Any = None,
    limit: int = CANDIDATES,
) -> dict[str, Any]:
    """Parse a one-line request.

    Returns ``{origin, dest, depart_at?, depart_time?, depart_date?, mode?, preference?, confidence,
    ambiguous: {origin, dest}, origin_candidates, dest_candidates, parsed: {...}}``. ``origin``/``dest`` are
    the best place dicts (or None when nothing matched); candidate lists are always included so a UI can show
    a picker when ``ambiguous`` is set.
    """
    if searcher is None:
        from zill.places.service import search as searcher
    if now is None:
        if tz is None:
            from zill.services import get_city

            tz = get_city(city_id).tz
        now = datetime.now(ZoneInfo(tz))
    raw = _clean(text.translate(_AR_DIGITS))
    t, hhmm, date_iso, iso = _extract_time(raw, now)
    t, mode, pref = _extract_options(t)
    splits = _splits(t)
    if not splits:
        side = _side(city_id, _FROM.sub("", t), searcher, limit) if t else None
        res: dict[str, Any] = {
            "origin": None,
            "dest": side["best"] if side else None,
            "origin_candidates": [],
            "dest_candidates": side["candidates"] if side else [],
            "ambiguous": {"origin": True, "dest": bool(side and side["ambiguous"])},
            "confidence": 0.0,
            "note": "Could not find two places; write it as 'from X to Y'.",
        }
    else:
        best_pair = None
        best_key = -1.0
        for a, b in splits[:6]:
            sa, sb = _side(city_id, a, searcher, limit), _side(city_id, b, searcher, limit)
            key = min(sa["confidence"], sb["confidence"]) + 0.01 * (sa["confidence"] + sb["confidence"])
            if key > best_key:
                best_key, best_pair = key, (sa, sb)
        assert best_pair is not None
        sa, sb = best_pair
        res = {
            "origin": sa["best"],
            "dest": sb["best"],
            "origin_candidates": sa["candidates"],
            "dest_candidates": sb["candidates"],
            "ambiguous": {"origin": sa["ambiguous"], "dest": sb["ambiguous"]},
            "confidence": round(min(sa["confidence"], sb["confidence"]), 2),
            "parsed": {"origin_text": sa["text"], "dest_text": sb["text"]},
        }
    if iso:
        res["depart_at"] = iso
    if hhmm:
        res["depart_time"] = hhmm
    if date_iso:
        res["depart_date"] = date_iso
    if mode:
        res["mode"] = mode
    if pref:
        res["preference"] = pref
    return res

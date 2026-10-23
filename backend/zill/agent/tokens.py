"""Token-resolved numbers (PRD 11.4): the anti-hallucination layer.

The model never writes a computed number. It writes `{{route.coolest.sun_saved_min}}`; the backend
resolves that path from the per-session ResultStore (tool outputs only) and substitutes the formatted
value. A numeric guard rejects any digit / spelled-out number that is neither a token nor present in
the user's own message.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from zill import config

TOKEN_RE = re.compile(r"\{\{\s*([A-Za-z0-9_.\-]+)\s*\}\}")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")

# Keys that are never worth sending to the model / counting as token paths.
HEAVY_KEYS = {"segments", "geometry", "latlon", "nodes", "edges", "geom", "polyline"}


class TokenError(Exception):
    """A token could not be resolved against the store."""


# ------------------------------------------------------------------------------------------------
# Store
# ------------------------------------------------------------------------------------------------
class ResultStore:
    """Per-session store of tool results under stable keys (`route`, `departure`, `place.origin`)."""

    def __init__(self, tz: str | None = None) -> None:
        self._data: dict[str, Any] = {}
        self.tz = ZoneInfo(tz or config.TIMEZONE)

    # -- writing -----------------------------------------------------------------------------
    def set(self, key: str, value: Any) -> None:
        parts = key.split(".")
        cur = self._data
        for p in parts[:-1]:
            nxt = cur.get(p)
            if not isinstance(nxt, dict):
                nxt = {}
                cur[p] = nxt
            cur = nxt
        cur[parts[-1]] = value

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self._lookup(key)[0]
        except TokenError:
            return default

    def has(self, key: str) -> bool:
        try:
            self._lookup(key)
            return True
        except TokenError:
            return False

    def keys(self) -> list[str]:
        return list(self._data.keys())

    def snapshot(self) -> dict[str, Any]:
        return self._data

    # -- resolving ---------------------------------------------------------------------------
    def _lookup(self, path: str) -> tuple[Any, str]:
        """Return (raw value, requested leaf key). Supports list indexes and derived fields."""
        parts = path.split(".")
        cur: Any = self._data
        for i, part in enumerate(parts):
            last = i == len(parts) - 1
            if isinstance(cur, dict):
                if part in cur:
                    cur = cur[part]
                    continue
                if last:
                    derived = _derive(cur, part, self.tz)
                    if derived is not _MISSING:
                        return derived, part
                raise TokenError(f"unresolved path '{path}' (missing '{part}')")
            if isinstance(cur, list):
                if part.lstrip("-").isdigit() and -len(cur) <= int(part) < len(cur):
                    cur = cur[int(part)]
                    continue
                raise TokenError(f"unresolved path '{path}' (bad list index '{part}')")
            raise TokenError(f"unresolved path '{path}' (cannot descend into scalar at '{part}')")
        return cur, parts[-1]

    def resolve_path(self, path: str) -> str:
        value, leaf = self._lookup(path)
        if isinstance(value, (dict, list)):
            raise TokenError(f"path '{path}' is not a scalar")
        return format_value(value, leaf, self.tz)

    def resolve(self, text: str) -> Resolution:
        resolved: list[dict[str, str]] = []
        unresolved: list[str] = []

        def sub(m: re.Match[str]) -> str:
            path = m.group(1)
            try:
                val = self.resolve_path(path)
            except TokenError:
                unresolved.append(path)
                return m.group(0)
            resolved.append({"token": path, "value": val})
            return val

        out = TOKEN_RE.sub(sub, text)
        return Resolution(text=out, resolved=resolved, unresolved=unresolved)

    # -- helpers for prompting ---------------------------------------------------------------
    def token_paths(self, key: str, limit: int = 60) -> list[str]:
        """List usable scalar token paths under `key` (including derived `_min`/`_time`)."""
        root = self.get(key)
        out: list[str] = []
        _walk_paths(root, key, out, limit)
        return out


@dataclass
class Resolution:
    text: str
    resolved: list[dict[str, str]] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.unresolved


# ------------------------------------------------------------------------------------------------
# Derived fields and formatting
# ------------------------------------------------------------------------------------------------
_MISSING = object()


def _parse_dt(v: Any, tz: ZoneInfo) -> datetime | None:
    if isinstance(v, datetime):
        return v.astimezone(tz) if v.tzinfo else v.replace(tzinfo=tz)
    if isinstance(v, str):
        try:
            d = datetime.fromisoformat(v)
        except ValueError:
            return None
        return d.astimezone(tz) if d.tzinfo else d.replace(tzinfo=tz)
    return None


def _derive(d: dict[str, Any], key: str, tz: ZoneInfo) -> Any:
    """Derived leaf fields: X_min from X_s, X_km from X_m, X_time from an ISO timestamp X."""
    if key.endswith("_min") and isinstance(d.get(key[:-4] + "_s"), (int, float)):
        return d[key[:-4] + "_s"] / 60.0
    if key.endswith("_km") and isinstance(d.get(key[:-3] + "_m"), (int, float)):
        return d[key[:-3] + "_m"] / 1000.0
    if key.endswith("_time"):
        base = d.get(key[:-5])
        dt = _parse_dt(base, tz)
        if dt is not None:
            return dt
    return _MISSING


def _fmt_num(v: float, nd: int) -> str:
    s = f"{v:.{nd}f}"
    return "0" + s[1:] if s.startswith(".") else s


def format_value(value: Any, leaf: str, tz: ZoneInfo) -> str:
    """Format by leaf-name suffix: _min, _pct, _time, _m, _km, _s, _c, else generic."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if value is None:
        raise TokenError(f"value for '{leaf}' is null")
    if isinstance(value, str):
        if leaf.endswith("_time"):
            dt = _parse_dt(value, tz)
            if dt is not None:
                return dt.strftime("%H:%M")
        return value
    if isinstance(value, datetime):
        return _parse_dt(value, tz).strftime("%H:%M")  # type: ignore[union-attr]
    v = float(value)
    if leaf.endswith("_time"):
        # seconds since midnight
        h, m = divmod(int(round(v / 60.0)), 60)
        return f"{h % 24:02d}:{m:02d}"
    if leaf.endswith("_min"):
        return f"{_fmt_num(v, 1)} min"
    if leaf.endswith("_pct"):
        return f"{_fmt_num(v, 0)}%"
    if leaf.endswith("_km"):
        return f"{_fmt_num(v, 1)} km"
    if leaf.endswith("_m"):
        return f"{_fmt_num(v, 0)} m"
    if leaf.endswith("_s"):
        return f"{_fmt_num(v, 0)} s"
    if leaf.endswith("_c"):
        return f"{_fmt_num(v, 1)} °C"
    if leaf.endswith("_deg"):  # sun altitude / azimuth
        return f"{_fmt_num(v, 0)}°"
    if leaf.endswith("_wm2"):  # irradiance
        return f"{_fmt_num(v, 0)} W/m²"
    if float(v).is_integer():
        return str(int(v))
    return _fmt_num(v, 1)


def _walk_paths(node: Any, prefix: str, out: list[str], limit: int, depth: int = 0) -> None:
    if len(out) >= limit or depth > 4:
        return
    if isinstance(node, dict):
        for k, v in node.items():
            if k in HEAVY_KEYS:
                continue
            _walk_paths(v, f"{prefix}.{k}", out, limit, depth + 1)
            if k.endswith("_s") and isinstance(v, (int, float)) and not isinstance(v, bool):
                out.append(f"{prefix}.{k[:-2]}_min")
            if k.endswith("_m") and isinstance(v, (int, float)) and not isinstance(v, bool):
                out.append(f"{prefix}.{k[:-2]}_km")
            if isinstance(v, str) and _parse_dt(v, ZoneInfo(config.TIMEZONE)) is not None and len(v) > 15:
                out.append(f"{prefix}.{k}_time")
    elif isinstance(node, list):
        for i, v in enumerate(node[:3]):
            _walk_paths(v, f"{prefix}.{i}", out, limit, depth + 1)
    elif isinstance(node, (int, float, str)) and not isinstance(node, bool):
        out.append(prefix)


# ------------------------------------------------------------------------------------------------
# Numeric guard
# ------------------------------------------------------------------------------------------------
_NUM_SPAN = re.compile(r"\d+(?:[:.,]\d+)*")
_LIST_NUM = re.compile(r"(?m)^(\s*)(\d{1,2}|[a-zA-Z])([.)])(\s)")
_NUMBER_WORDS = (
    "two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen "
    "eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred thousand million "
    "billion dozen half quarter twice thrice"
).split()
_WORD_RE = re.compile(r"\b(" + "|".join(_NUMBER_WORDS) + r")\b", re.I)
_ONE_UNIT_RE = re.compile(
    r"\bone\s+(?:more\s+|extra\s+)?(?:minute|min|hour|hr|second|sec|degree|percent|per\s*cent|metre|meter|"
    r"km|kilometre|kilometer|mile|stop|block|drop|task|time)s?\b",
    re.I,
)
_PERCENT_WORD = re.compile(r"\bper\s*cent\b|\bpercent\b", re.I)


def _ascii_digits(s: str) -> str:
    """Map any Unicode decimal digit to ASCII; leave everything else alone."""
    out = []
    for ch in s:
        if ch.isdigit():
            try:
                out.append(str(unicodedata.digit(ch)))
                continue
            except ValueError:
                pass
        out.append(ch)
    return "".join(out)


def _vulgar_fraction_chars(s: str) -> list[str]:
    """Characters with a numeric value that are not decimal digits (1/2, superscripts, roman, ...)."""
    out = []
    for ch in s:
        if ch.isdigit():
            continue
        try:
            if unicodedata.numeric(ch, None) is not None and not ch.isalpha():
                out.append(ch)
        except (TypeError, ValueError):
            continue
    return out


def _spans(text: str) -> set[str]:
    return {m.group(0).replace(",", "") for m in _NUM_SPAN.finditer(_ascii_digits(text))}


def _user_allowed(user_text: str) -> tuple[set[str], set[str]]:
    nums = _spans(user_text or "")
    words = {m.group(1).lower() for m in _WORD_RE.finditer(user_text or "")}
    return nums, words


def find_violations(text: str, user_text: str = "") -> list[str]:
    """Return the offending numeric snippets in model text (tokens are stripped first).

    Allowed: numbers/words present in the user's own message, list numbering at line start,
    ordinal words (first, second, ...). Everything else is a bare computed number.
    """
    body = TOKEN_RE.sub(" ", text)
    body = _LIST_NUM.sub(lambda m: m.group(1) + m.group(4), body)  # list numbering
    norm = _ascii_digits(body)
    allowed_nums, allowed_words = _user_allowed(user_text)
    bad: list[str] = []
    for m in _NUM_SPAN.finditer(norm):
        span = m.group(0)
        key = span.replace(",", "")
        if key in allowed_nums:
            continue
        # a decimal such as 4.5 the user wrote as "4.5" is covered above; "13:30" likewise
        bad.append(span)
    for ch in _vulgar_fraction_chars(body):
        bad.append(ch)
    for m in _WORD_RE.finditer(body):
        if m.group(1).lower() not in allowed_words:
            bad.append(m.group(0))
    for m in _ONE_UNIT_RE.finditer(body):
        if "one" not in allowed_words and not re.search(r"\bone\b", user_text or "", re.I):
            bad.append(m.group(0))
    return bad


def check_text(text: str, store: ResultStore, user_text: str = "") -> list[str]:
    """Defects for a model-authored text: unresolved tokens + bare numbers. Empty list = clean."""
    defects: list[str] = []
    res = store.resolve(text)
    for u in res.unresolved:
        defects.append(f"unresolved token {{{{{u}}}}}")
    for b in find_violations(text, user_text):
        defects.append(f"bare number '{b}' (use a {{{{token}}}} from a tool result)")
    return defects


def redact_bare_numbers(text: str, user_text: str = "") -> tuple[str, int]:
    """Rewrite fallback: drop every sentence/line that contains a violation. Returns (text, dropped)."""
    pieces = _SENTENCE_SPLIT.split(text)
    kept, dropped = [], 0
    for p in pieces:
        if not p.strip():
            continue
        if find_violations(p, user_text):
            dropped += 1
        else:
            kept.append(p.strip())
    return " ".join(kept), dropped


def count_claims(text: str) -> int:
    """Number of checkable claims = distinct tokens in the text (min 1 per sentence with a token)."""
    return len(TOKEN_RE.findall(text))

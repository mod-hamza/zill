"""Optional online geocoding fallback (Nominatim), used only when the local index has no good match.

Polite by construction: bounded to the city bbox, our own User-Agent (no email), at most one request per
second process-wide, 2 s timeout, results cached. Disabled with ``ZILL_ONLINE_GEOCODE=0``. The HTTP layer is
the swappable ``transport`` so tests never touch the network.
"""

from __future__ import annotations

import os
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

import httpx

from zill.places.fold import fold

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "Zill-hackathon-prototype/0.1"
TIMEOUT_S = 2.0
MIN_INTERVAL_S = 1.0
MAX_WAIT_S = 1.5  # if the global 1 req/s budget would make us wait longer than this, skip the lookup
CACHE_SIZE = 512
CACHE_TTL_S = 3600.0
FAIL_TTL_S = 60.0

Transport = Callable[[str, dict[str, Any]], list[dict[str, Any]]]


def _http_get(url: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    r = httpx.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_S)
    r.raise_for_status()
    return r.json()


transport: Transport = _http_get  # tests monkeypatch this

_LOCK = threading.Lock()
_last_call = 0.0
_CACHE: OrderedDict[tuple[str, str], tuple[float, list[dict[str, Any]]]] = OrderedDict()
_REGISTRY: OrderedDict[tuple[str, str], dict[str, Any]] = OrderedDict()  # (city, id) -> place


def enabled() -> bool:
    return os.environ.get("ZILL_ONLINE_GEOCODE", "1").strip().lower() not in ("0", "false", "no", "off")


def _acquire_slot() -> bool:
    """Reserve the next 1 req/s slot; False when it is too far away to be worth waiting for."""
    global _last_call
    with _LOCK:
        now = time.monotonic()
        wait = max(0.0, _last_call + MIN_INTERVAL_S - now)
        if wait > MAX_WAIT_S:
            return False
        _last_call = now + wait
    if wait > 0:
        time.sleep(wait)
    return True


def remember(city_id: str, place: dict[str, Any]) -> None:
    with _LOCK:
        _REGISTRY[(city_id, place["id"])] = place
        while len(_REGISTRY) > CACHE_SIZE:
            _REGISTRY.popitem(last=False)


def recall(city_id: str, place_id: str) -> dict[str, Any] | None:
    with _LOCK:
        return _REGISTRY.get((city_id, place_id))


def clear() -> None:
    global _last_call
    with _LOCK:
        _CACHE.clear()
        _REGISTRY.clear()
        _last_call = 0.0


def search(city_id: str, bbox: dict[str, float], query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Nominatim results inside ``bbox`` as place dicts (``source: "online"``); [] on any failure."""
    if not enabled():
        return []
    q = fold(query)
    if len(q) < 3:
        return []
    key = (city_id, q)
    now = time.monotonic()
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < (CACHE_TTL_S if hit[1] else FAIL_TTL_S):
            _CACHE.move_to_end(key)
            return [dict(p) for p in hit[1][:limit]]
    out: list[dict[str, Any]] = []
    if _acquire_slot():
        params = {
            "q": query.strip()[:200],
            "format": "jsonv2",
            "limit": max(1, min(limit, 10)),
            "viewbox": f"{bbox['w']},{bbox['n']},{bbox['e']},{bbox['s']}",
            "bounded": 1,
            "accept-language": "en",
        }
        try:
            rows = transport(NOMINATIM_URL, params)
        except Exception:  # noqa: BLE001 - offline / timeout / rate-limited: just no online result
            rows = []
        for r in rows or []:
            try:
                lat, lon = float(r["lat"]), float(r["lon"])
            except (KeyError, TypeError, ValueError):
                continue
            if not (bbox["s"] <= lat <= bbox["n"] and bbox["w"] <= lon <= bbox["e"]):
                continue
            name = (r.get("name") or str(r.get("display_name", "")).split(",")[0]).strip()
            if not name:
                continue
            pid = f"online_{str(r.get('osm_type', 'x'))[:1]}{r.get('osm_id', int(lat * 1e5))}"
            out.append(
                {
                    "id": pid,
                    "name": name,
                    "alt_names": [],
                    "kind": "other",
                    "lat": round(lat, 7),
                    "lon": round(lon, 7),
                    "source": "online",
                    "label": str(r.get("display_name", ""))[:160],
                }
            )
    with _LOCK:
        _CACHE[key] = (time.monotonic(), out)
        while len(_CACHE) > CACHE_SIZE:
            _CACHE.popitem(last=False)
    return [dict(p) for p in out[:limit]]

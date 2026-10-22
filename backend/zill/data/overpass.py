"""Overpass API client with tiling, mirror rotation, backoff and an on-disk raw cache (PRD 6.3).

Every raw response is cached at ``data/raw/<city_id>/<sha1(query)>.json``; re-runs hit the cache.
Elements are deduplicated by ``type/id`` across tiles.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from zill import config

log = logging.getLogger("zill.data.overpass")

USER_AGENT = "Zill-hackathon-prototype/0.1"
TIMEOUT_S = 180
MAX_TRIES = 5
RAW_DIR = config.DATA_DIR / "raw"

BBox = dict[str, float]  # {"s","w","n","e"}

# Pluggable transport: (url, query) -> parsed JSON. Tests monkeypatch this to disable network.
Transport = Callable[[str, str], dict[str, Any]]


def _http_post(url: str, query: str) -> dict[str, Any]:
    with httpx.Client(timeout=TIMEOUT_S + 30, headers={"User-Agent": USER_AGENT}) as client:
        r = client.post(url, data={"data": query})
        if r.status_code in (429, 502, 503, 504):
            raise httpx.HTTPStatusError(f"overpass busy {r.status_code}", request=r.request, response=r)
        r.raise_for_status()
        return r.json()


transport: Transport = _http_post


class FetchStats:
    def __init__(self) -> None:
        self.requests = 0
        self.cache_hits = 0
        self.endpoint: str | None = None
        self.osm_timestamp: str | None = None


STATS = FetchStats()


def tile_bbox(bbox: BBox, nx: int = 4, ny: int = 4) -> list[BBox]:
    ds = (bbox["n"] - bbox["s"]) / ny
    dw = (bbox["e"] - bbox["w"]) / nx
    tiles = []
    for j in range(ny):
        for i in range(nx):
            tiles.append(
                {
                    "s": round(bbox["s"] + j * ds, 7),
                    "n": round(bbox["s"] + (j + 1) * ds, 7),
                    "w": round(bbox["w"] + i * dw, 7),
                    "e": round(bbox["w"] + (i + 1) * dw, 7),
                }
            )
    return tiles


def bbox_str(b: BBox) -> str:
    return f"{b['s']},{b['w']},{b['n']},{b['e']}"


def run_query(
    query: str, city_id: str, refresh: bool = False, urls: list[str] | None = None
) -> dict[str, Any]:
    """POST a query (cached). Rotates mirrors with exponential backoff, MAX_TRIES attempts."""
    key = hashlib.sha1(query.encode("utf-8")).hexdigest()
    cache_dir = RAW_DIR / city_id
    path = cache_dir / f"{key}.json"
    if path.exists() and not refresh:
        STATS.cache_hits += 1
        data = json.loads(path.read_text(encoding="utf-8"))
        _note_meta(data)
        return data
    urls = urls or config.OVERPASS_URLS
    last_err: Exception | None = None
    for attempt in range(MAX_TRIES):
        url = urls[attempt % len(urls)]
        try:
            STATS.requests += 1
            data = transport(url, query)
            if "elements" not in data:
                raise ValueError(f"no elements in response: {str(data)[:200]}")
            remark = data.get("remark", "")
            if remark and "runtime error" in remark.lower():
                raise ValueError(f"overpass runtime error: {remark[:200]}")
            data.setdefault("_zill", {})
            data["_zill"].update({"endpoint": url, "fetched_at": datetime.now(UTC).isoformat()})
            cache_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
            _note_meta(data)
            return data
        except Exception as e:  # noqa: BLE001 - any transport failure triggers retry
            last_err = e
            wait = min(120.0, 5.0 * (2**attempt))
            log.warning("overpass attempt %d at %s failed: %s; retry in %.0fs", attempt + 1, url, e, wait)
            if attempt < MAX_TRIES - 1:
                time.sleep(wait)
    raise RuntimeError(f"Overpass failed after {MAX_TRIES} tries: {last_err}")


def _note_meta(data: dict[str, Any]) -> None:
    z = data.get("_zill", {})
    if z.get("endpoint"):
        STATS.endpoint = z["endpoint"]
    ts = (data.get("osm3s") or {}).get("timestamp_osm_base")
    if ts and (STATS.osm_timestamp is None or ts > STATS.osm_timestamp):
        STATS.osm_timestamp = ts


def fetch_tiled(
    body: str,
    bbox: BBox,
    city_id: str,
    nx: int = 4,
    ny: int = 4,
    refresh: bool = False,
    out: str = "out body geom;",
) -> list[dict[str, Any]]:
    """Run ``body`` (with ``{bbox}`` placeholders) per tile and merge elements deduped by type/id."""
    seen: dict[str, dict[str, Any]] = {}
    for t in tile_bbox(bbox, nx, ny):
        q = f"[out:json][timeout:{TIMEOUT_S}];({body.format(bbox=bbox_str(t))});{out}"
        data = run_query(q, city_id, refresh=refresh)
        for el in data["elements"]:
            seen.setdefault(f"{el['type']}/{el['id']}", el)
    return list(seen.values())


# --- query bodies (Overpass QL; {bbox} replaced per tile) ------------------------------------------
Q_BUILDINGS = (
    'way["building"]({bbox});way["building:part"]({bbox});'
    'rel["building"]({bbox});rel["building:part"]({bbox});'
)
Q_ROADS = (
    'way["highway"]({bbox});'
    'node["highway"~"^(crossing|traffic_signals|elevator)$"]({bbox});'
    'node["entrance"]({bbox});node["railway"~"^(crossing|subway_entrance)$"]({bbox});'
    'way["indoor"]({bbox});'
)
Q_TREES = 'node["natural"="tree"]({bbox});way["natural"="tree_row"]({bbox});'
Q_POIS = 'nwr["name"]({bbox});'


def fetch_buildings(bbox: BBox, city_id: str, refresh: bool = False) -> list[dict[str, Any]]:
    return fetch_tiled(Q_BUILDINGS, bbox, city_id, refresh=refresh)


def fetch_roads(bbox: BBox, city_id: str, refresh: bool = False) -> list[dict[str, Any]]:
    return fetch_tiled(Q_ROADS, bbox, city_id, refresh=refresh)


def fetch_trees(bbox: BBox, city_id: str, refresh: bool = False) -> list[dict[str, Any]]:
    return fetch_tiled(Q_TREES, bbox, city_id, nx=2, ny=2, refresh=refresh)


def fetch_pois(bbox: BBox, city_id: str, refresh: bool = False) -> list[dict[str, Any]]:
    return fetch_tiled(Q_POIS, bbox, city_id, nx=2, ny=2, refresh=refresh, out="out tags center;")


def raw_dir(city_id: str) -> Path:
    return RAW_DIR / city_id

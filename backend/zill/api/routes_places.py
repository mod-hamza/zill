"""Typed places: GET /api/places/search and POST /api/places/parse (Stream E, overnight)."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from zill.api.common import ORJSON, ApiError
from zill.places import online
from zill.places.index import get_index
from zill.places.parse import parse_text
from zill.places.service import search as search_places
from zill.services import get_city

router = APIRouter(prefix="/api/places", tags=["places"], default_response_class=ORJSON)

MAX_QUERY = 200
MAX_TEXT = 300
PUBLIC_KEYS = (
    "id", "name", "alt_names", "kind", "lat", "lon", "x", "z", "node", "snap_m", "score", "source",
    "matched", "label", "curated",
)  # fmt: skip


def _public(p: dict[str, Any] | None) -> dict[str, Any] | None:
    return None if p is None else {k: p[k] for k in PUBLIC_KEYS if k in p and p[k] is not None}


class ParseRequest(BaseModel):
    city: str
    text: str = Field(min_length=1, max_length=MAX_TEXT)


@router.get("/search")
def get_search(
    city: str = Query(...),
    q: str = Query(..., min_length=1, max_length=MAX_QUERY),
    limit: int = Query(8, ge=1, le=20),
    online_fallback: bool = Query(True, alias="online"),
) -> dict[str, Any]:
    """Ranked places matching ``q`` (accent/case-insensitive, prefix + token + fuzzy)."""
    t0 = time.perf_counter()
    get_city(city)  # 404 for unknown cities
    hits = search_places(city, q, limit=limit, use_online=online_fallback)
    return {
        "city": city,
        "q": q,
        "results": [_public(h) for h in hits],
        "online_enabled": online.enabled(),
        "timing_ms": round((time.perf_counter() - t0) * 1000, 2),
    }


@router.get("/stats")
def get_stats(city: str = Query(...)) -> dict[str, Any]:
    get_city(city)
    ix = get_index(city)
    kinds: dict[str, int] = {}
    for p in ix.places:
        kinds[p["kind"]] = kinds.get(p["kind"], 0) + 1
    return {"city": city, "count": len(ix), "by_kind": dict(sorted(kinds.items()))}


@router.post("/parse")
def post_parse(req: ParseRequest) -> dict[str, Any]:
    """Parse "from X to Y at 15:30 by bike, sunny" into places, time, mode and preference."""
    t0 = time.perf_counter()
    ctx = get_city(req.city)
    if not req.text.strip():
        raise ApiError(422, "empty_text", "text is empty")
    res = parse_text(req.city, req.text, tz=ctx.tz)
    for k in ("origin", "dest"):
        res[k] = _public(res.get(k))
        res[f"{k}_candidates"] = [_public(c) for c in res.get(f"{k}_candidates", [])]
    res["city"] = req.city
    res["timing_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    return res

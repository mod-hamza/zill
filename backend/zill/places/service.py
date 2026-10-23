"""Search = local index first, online fallback only when the index has no good match."""

from __future__ import annotations

from typing import Any

from zill.places import online
from zill.places.index import get_index

GOOD_SCORE = 80.0  # a local hit at or above this is "good": no online lookup


def _city_bbox(city_id: str) -> dict[str, float]:
    from zill.services import get_city

    meta = get_city(city_id).meta
    return meta.get("bbox_scene") or meta["bbox_core"]


def search(city_id: str, query: str, limit: int = 8, use_online: bool = True) -> list[dict[str, Any]]:
    """Ranked places for ``query``. Online results (labelled ``source: "online"``) are appended only when
    the best local score is below ``GOOD_SCORE`` and each is verified routable (snaps to the walk graph)."""
    hits = get_index(city_id).search(query, limit=limit)
    if use_online and online.enabled() and (not hits or hits[0]["score"] < GOOD_SCORE):
        try:
            from zill.services import PlaceError, get_city

            ctx = get_city(city_id)
            for p in online.search(city_id, _city_bbox(city_id), query, limit=min(limit, 5)):
                try:
                    r = ctx.resolve_place({"lat": p["lat"], "lon": p["lon"], "name": p["name"]}, "walk")
                except PlaceError:
                    continue
                p.update(x=r["x"], z=r["z"], node=r["node"], snap_m=r["snap_m"], score=60.0)
                online.remember(city_id, p)
                hits.append(p)
        except Exception:  # noqa: BLE001 - the fallback must never break the local answer
            pass
    return hits[:limit]

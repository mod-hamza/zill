"""Health, weather, gazetteer and on-demand shade computation endpoints (PRD 9, 10)."""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query

from zill import config
from zill import weather as weather_mod
from zill.api.common import ORJSON, ApiError
from zill.api.schemas import GazetteerResponse, ShadeComputeRequest, WeatherResponse
from zill.api.sse import run_in_thread_sse, sse_response
from zill.services import CityNotFound, city_dir, get_city, list_city_ids

router = APIRouter(prefix="/api", tags=["misc"], default_response_class=ORJSON)
VERSION = "0.1.0"


# ---- health ------------------------------------------------------------------------------------
def health_payload() -> dict[str, Any]:
    """Liveness + what is actually loaded: city, shade presets, replay, LLM (no network calls)."""
    out: dict[str, Any] = {
        "ok": True,
        "service": "zill",
        "version": VERSION,
        "replay": config.REPLAY,
        "llm": {
            "base_url": config.LLM_BASE_URL,
            "model": config.MODEL,
            "key_present": bool(config.LLM_API_KEY),
        },
    }
    city: dict[str, Any] = {"id": config.DEFAULT_CITY, "loaded": False, "available": list_city_ids()}
    shade: dict[str, Any] = {"presets": {}, "all_present": False}
    try:
        ctx = get_city(config.DEFAULT_CITY)
        city.update(
            loaded=True,
            name=ctx.meta.get("name"),
            nodes=ctx.graph.n_nodes,
            edges=ctx.graph.n_edges,
            pois=len(ctx.pois),
            buildings=ctx.meta.get("counts", {}).get("buildings"),
        )
        for k in ctx.dates:
            shade["presets"][k] = (ctx.path / f"exposure_{k}.npz").exists() and (
                ctx.path / "shade" / k
            ).is_dir()
        shade["all_present"] = bool(shade["presets"]) and all(shade["presets"].values())
    except Exception as e:  # not baked yet is a valid state to report
        city["error"] = type(e).__name__
    out["city"], out["shade"] = city, shade
    rdir = config.REPLAY_DIR
    names = sorted(p.stem for p in rdir.glob("*.json")) if rdir.is_dir() else []
    out["replay_available"] = bool(names)
    out["replay_sessions"] = names
    try:  # agent module is owned by another stream; report what it says without calling the network
        import zill.agent.llm as llm_mod

        out["agent"] = {"module": True}
        fn = getattr(llm_mod, "status", None) or getattr(llm_mod, "health", None)
        if callable(fn):
            out["agent"].update(fn())
    except Exception:
        out["agent"] = {"module": False}
    return out


# ---- weather -----------------------------------------------------------------------------------
@router.get("/weather", response_model=WeatherResponse)
def get_weather(
    city: str = Query(default=config.DEFAULT_CITY),
    at: str | None = Query(default=None),
    hourly: bool = Query(default=False),
) -> dict[str, Any]:
    ctx = get_city(city)
    tz = ZoneInfo(ctx.tz)
    try:
        ts = datetime.fromisoformat(at.replace("Z", "+00:00")) if at else datetime.now(tz)
    except ValueError:
        raise ApiError(422, "bad_time", f"Could not parse time {at!r}; use ISO-8601") from None
    ts = ts.replace(tzinfo=tz) if ts.tzinfo is None else ts.astimezone(tz)
    res = weather_mod.get(city, ts)
    if not hourly:
        res = {**res, "hourly": []}
    return res


# ---- gazetteer ---------------------------------------------------------------------------------
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]+", " ", s).strip()


def _aliases(city_id: str) -> dict[str, list[str]]:
    """Curated aliases: data/curated/<city>/gazetteer.json `match` lists, by poi id."""
    p = config.DATA_DIR / "curated" / city_id / "gazetteer.json"
    if not p.exists():
        return {}
    try:
        return {e["id"]: list(e.get("match", [])) for e in json.loads(p.read_text(encoding="utf-8"))}
    except Exception:
        return {}


def search_pois(city_id: str, q: str, limit: int = 8) -> list[dict[str, Any]]:
    ctx = get_city(city_id)
    nq = _norm(q)
    if not nq:
        return []
    qt = set(nq.split())
    aliases = _aliases(city_id)
    hits = []
    for p in ctx.pois:
        names = [p["name"], p["id"].replace("_", " "), *aliases.get(p["id"], [])]
        best = 0.0
        for nm in names:
            n = _norm(nm)
            if not n:
                continue
            nt = set(n.split())
            overlap = sum(
                max(
                    (1.0 if (t == u or u.startswith(t)) else SequenceMatcher(None, t, u).ratio() for u in nt),
                    default=0.0,
                )
                >= 0.8
                for t in qt
            ) / len(qt)
            sub = 1.0 if (nq in n or n in nq) else 0.0
            prefix = 1.0 if n.startswith(nq) or any(t.startswith(nq) for t in nt) else 0.0
            ratio = SequenceMatcher(None, nq, n).ratio()
            score = 0.45 * overlap + 0.25 * sub + 0.15 * prefix + 0.15 * ratio
            if nq == n:
                score = 2.0
            best = max(best, score)
        if best >= 0.3:
            hits.append(
                {
                    "id": p["id"],
                    "name": p["name"],
                    "lat": p["lat"],
                    "lon": p["lon"],
                    "kind": p.get("kind"),
                    "node": p.get("node"),
                    "score": round(best, 3),
                    "source": "gazetteer",
                }
            )
    hits.sort(key=lambda h: -h["score"])
    return hits[:limit]


def _nominatim(q: str, bbox: dict[str, float]) -> list[dict[str, Any]]:
    import httpx

    params = {
        "q": q,
        "format": "jsonv2",
        "limit": "5",
        "bounded": "1",
        "viewbox": f"{bbox['w']},{bbox['n']},{bbox['e']},{bbox['s']}",
    }
    with httpx.Client(timeout=2.0, headers={"User-Agent": "Zill-hackathon-prototype/0.1"}) as c:
        r = c.get("https://nominatim.openstreetmap.org/search", params=params)
        r.raise_for_status()
        out = []
        for it in r.json():
            out.append(
                {
                    "id": f"osm_{it.get('osm_type', 'x')}_{it.get('osm_id', '')}",
                    "name": it.get("display_name", q),
                    "lat": float(it["lat"]),
                    "lon": float(it["lon"]),
                    "kind": it.get("category"),
                    "node": None,
                    "score": 0.5,
                    "source": "nominatim",
                }
            )
        return out


@router.get("/gazetteer/{city}", response_model=GazetteerResponse)
def gazetteer(
    city: str, q: str = Query(default="", max_length=120), limit: int = Query(default=8, ge=1, le=25)
) -> dict[str, Any]:
    results = search_pois(city, q, limit)
    online = False
    if not results and q.strip() and config.GAZETTEER_ONLINE:
        try:
            bbox = get_city(city).meta["bbox_core"]
            results = _nominatim(q, bbox)
            online = True
        except Exception:
            results = []  # offline or slow: local gazetteer only
    return {"query": q, "results": results, "online_fallback": online}


# ---- on-demand shade ---------------------------------------------------------------------------
@router.post("/shade/compute")
async def shade_compute(req: ShadeComputeRequest):
    """SSE progress while the shade engine computes a date (requested step first), then `done`."""
    try:
        city_dir(req.city)
    except CityNotFound:
        raise ApiError(404, "city_not_found", f"Unknown city {req.city!r}") from None
    if not re.fullmatch(r"[A-Za-z0-9\-]+", req.date):
        raise ApiError(422, "bad_date", "date must be a preset id or YYYY-MM-DD")
    if req.first_hhmm is not None and not re.fullmatch(r"\d{4}", req.first_hhmm):
        raise ApiError(422, "bad_time", "first_hhmm must look like '1330'")

    def work(emit):  # type: ignore[no-untyped-def]
        from zill.shade.cache import compute_date

        def cb(done: int, total: int, hhmm: str) -> None:
            emit(
                "progress",
                {"done": done, "total": total, "hhmm": hhmm, "pct": round(100.0 * done / max(total, 1), 1)},
            )

        emit("started", {"city": req.city, "date": req.date})
        idx = compute_date(req.city, req.date, cb, first_hhmm=req.first_hhmm)
        # make sure the routing layer sees the fresh table
        ctx = get_city(req.city)
        ctx._tables.pop(ctx.date_for(req.date)[0], None)
        return {
            "city": req.city,
            "date": idx.get("date"),
            "date_id": idx.get("date_id"),
            "steps": len(idx.get("steps", [])),
            "timing": idx.get("timing"),
        }

    return sse_response(run_in_thread_sse(work))

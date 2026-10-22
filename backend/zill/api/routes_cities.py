"""Cities, baked files, shade rasters, sun position (PRD 10; CONTRACTS 3)."""

from __future__ import annotations

import asyncio
import io
import json
import mimetypes
import re
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, Response

from zill import config
from zill.api.common import ORJSON, ApiError
from zill.api.schemas import BuildEvent, CityListItem, SunResponse
from zill.api.sse import sse_event, sse_response
from zill.services import CityNotFound, city_dir, get_city, list_city_ids

router = APIRouter(prefix="/api", tags=["cities"], default_response_class=ORJSON)

CACHE_CONTROL = "public, max-age=86400"
MIME = {
    ".glb": "model/gltf-binary",
    ".gltf": "model/gltf+json",
    ".json": "application/json",
    ".geojson": "application/geo+json",
    ".png": "image/png",
    ".npz": "application/octet-stream",
    ".bin": "application/octet-stream",
    ".webp": "image/webp",
}
_HHMM = re.compile(r"^\d{4}$")


def _cached_file(request: Request, target: Path, mime: str) -> Response:
    """FileResponse with a strong-ish ETag (mtime+size) and 304 handling."""
    st = target.stat()
    etag = f'"{st.st_mtime_ns:x}-{st.st_size:x}"'
    headers = {"Cache-Control": CACHE_CONTROL, "ETag": etag}
    inm = request.headers.get("if-none-match")
    if inm and etag in [t.strip() for t in inm.split(",")]:
        return Response(status_code=304, headers=headers)
    return FileResponse(target, media_type=mime, headers=headers)


def _read_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def _shade_log(cdir: Path) -> list[dict[str, Any]]:
    p = cdir / "shade" / "bake_log.json"
    if not p.exists():
        return []
    try:
        raw = _read_json(p)
    except Exception:
        return []
    if isinstance(raw, dict):
        raw = raw.get("build_log") or raw.get("steps") or raw.get("log") or []
    return [r for r in raw if isinstance(r, dict)]


def merged_build_log(cdir: Path, meta: dict[str, Any]) -> list[dict[str, Any]]:
    base = list(meta.get("build_log") or [])
    extra = _shade_log(cdir)
    if not extra:
        return base
    offset = max((int(r.get("t_ms", 0)) for r in base), default=0)
    first = min((int(r.get("t_ms", 0)) for r in extra), default=0)
    shift = offset if first < offset else 0
    for r in extra:
        r2 = dict(r)
        r2["t_ms"] = int(r.get("t_ms", 0)) + shift
        base.append(r2)
    return base


def city_status(cdir: Path, meta: dict[str, Any]) -> tuple[str, list[str]]:
    dates = meta.get("dates") or config.PRESET_DATES
    have = [d for d in dates if (cdir / f"exposure_{d}.npz").exists()]
    ok = (
        (cdir / "graph.json").exists()
        and (cdir / "buildings.json").exists()
        or (cdir / "graph.json").exists()
    )
    if ok and have:
        return "ready", have
    return ("partial" if ok else "incomplete"), have


@router.get("/cities", response_model=list[CityListItem])
def list_cities() -> list[dict[str, Any]]:
    out = []
    for cid in list_city_ids():
        cdir = city_dir(cid)
        meta = _read_json(cdir / "meta.json")
        status, have = city_status(cdir, meta)
        out.append(
            {
                "id": cid,
                "name": meta.get("name", cid),
                "origin": meta.get("origin"),
                "bbox": meta.get("bbox_core"),
                "counts": meta.get("counts", {}),
                "status": status,
                "shade_dates": have,
                "timezone": meta.get("timezone", config.TIMEZONE),
                "dates": meta.get("dates") or config.PRESET_DATES,
            }
        )
    return out


@router.get("/cities/{city_id}/meta")
def city_meta(city_id: str) -> dict[str, Any]:
    cdir = city_dir(city_id)
    meta = _read_json(cdir / "meta.json")
    meta["build_log"] = merged_build_log(cdir, meta)
    status, have = city_status(cdir, meta)
    meta["status"] = status
    meta["shade_dates"] = have
    return meta


@router.get("/cities/{city_id}/files/{path:path}")
def city_file(request: Request, city_id: str, path: str) -> Response:
    cdir = city_dir(city_id).resolve()
    if not path or "\x00" in path or ".." in Path(path.replace("\\", "/")).parts:
        raise ApiError(400, "bad_path", "Invalid file path")
    target = (cdir / path).resolve()
    try:
        target.relative_to(cdir)
    except ValueError:
        raise ApiError(400, "bad_path", "Invalid file path") from None
    if not target.is_file():
        raise ApiError(404, "file_not_found", f"No such file: {path}")
    mime = (
        MIME.get(target.suffix.lower()) or mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    )
    return _cached_file(request, target, mime)


@router.get("/shade/{city_id}/{date_id}/{hhmm}.png")
def shade_png(request: Request, city_id: str, date_id: str, hhmm: str) -> Response:
    cdir = city_dir(city_id).resolve()
    if not _HHMM.match(hhmm) or not re.fullmatch(r"[A-Za-z0-9\-]+", date_id):
        raise ApiError(400, "bad_request", "Expected /api/shade/{city}/{date_id}/{HHMM}.png")
    p = cdir / "shade" / date_id / f"step_{hhmm}.png"
    if p.is_file():
        return _cached_file(request, p, "image/png")
    try:  # on-demand dates cached by the shade stream (data/cache/...)
        from zill.shade.cache import get_shade_step

        arr = get_shade_step(city_id, date_id, hhmm)
        from PIL import Image

        buf = io.BytesIO()
        Image.fromarray(arr).save(buf, format="PNG", optimize=True)
        return Response(buf.getvalue(), media_type="image/png", headers={"Cache-Control": CACHE_CONTROL})
    except Exception:
        raise ApiError(404, "shade_not_found", f"No shade raster for {date_id} {hhmm}") from None


def _parse_at(at: str | None, tz: str) -> datetime:
    if not at:
        return datetime.now(ZoneInfo(tz))
    try:
        d = datetime.fromisoformat(at.replace("Z", "+00:00"))
    except ValueError:
        raise ApiError(422, "bad_time", f"Could not parse time {at!r}; use ISO-8601") from None
    return d if d.tzinfo else d.replace(tzinfo=ZoneInfo(tz))


@router.get("/sun", response_model=SunResponse)
def sun(
    city: str = Query(default=config.DEFAULT_CITY), at: str | None = Query(default=None)
) -> dict[str, Any]:
    ctx = get_city(city)
    tz = ctx.tz
    ts = _parse_at(at, tz).astimezone(ZoneInfo(tz))
    o = ctx.origin
    from zill.sun.position import sun_position, sun_times

    sp = sun_position(ts, o["lat"], o["lon"], tz)
    st = sun_times(date(ts.year, ts.month, ts.day), o["lat"], o["lon"], tz)
    return {
        "city": city,
        "at": ts.isoformat(),
        "alt_deg": round(sp.alt_deg, 3),
        "az_deg": round(sp.az_deg, 3),
        "vector": [round(v, 6) for v in sp.vector],
        "is_night": bool(sp.is_night),
        "sunrise": st["sunrise"].isoformat(),
        "sunset": st["sunset"].isoformat(),
        "solar_noon": st["solar_noon"].isoformat(),
    }


@router.post("/cities/build")
async def build_city(
    body: dict[str, Any] | None = None,
    city: str | None = Query(default=None),
    speed: float = Query(default=1.0, gt=0, le=100),
    live: bool = Query(default=False),
):
    """SSE replay of the recorded build log (real step timings), labelled mode=cached.

    `?live=1` is accepted but a live rebuild is not run from the API in this prototype: the stream
    stays in cached mode and says so (honest labelling).
    """
    body = body or {}
    cid = city or body.get("city") or body.get("city_id") or body.get("query") or config.DEFAULT_CITY
    try:
        cdir = city_dir(str(cid))
    except CityNotFound:
        # allow a free-text name ("Downtown Dubai") to match a baked city by name
        match = None
        for c in list_city_ids():
            if str(cid).strip().lower() in (
                c.lower(),
                str(_read_json(city_dir(c) / "meta.json").get("name", "")).lower(),
            ):
                match = c
        if match is None:
            raise ApiError(
                404, "city_not_found", f"No baked city matches {cid!r}; only baked cities can be shown"
            ) from None
        cdir = city_dir(match)
        cid = match
    meta = _read_json(cdir / "meta.json")
    log = merged_build_log(cdir, meta)
    note = "Replaying the recorded build log" + (" (live build is not run from the API)" if live else "")

    async def gen():
        yield sse_event(
            "build",
            BuildEvent(
                step="started",
                label=f"Building {meta.get('name', cid)}",
                mode="cached",
                t_ms=0,
                note=note,
                city=str(cid),
            ).model_dump(),
        )
        t_prev = 0.0
        for rec in log:
            t = float(rec.get("t_ms", 0))
            await asyncio.sleep(max(0.0, (t - t_prev) / 1000.0 / speed))
            t_prev = max(t_prev, t)
            ev = BuildEvent(
                step=str(rec.get("step", "step")),
                label=str(rec.get("label", rec.get("step", ""))),
                count=rec.get("count"),
                mode="cached",
                t_ms=int(t),
                city=str(cid),
                extra={k: v for k, v in rec.items() if k not in ("step", "label", "count", "t_ms")},
            )
            yield sse_event("build", ev.model_dump())
        yield sse_event(
            "ready",
            {
                "city": cid,
                "mode": "cached",
                "counts": meta.get("counts", {}),
                "elapsed_ms": int(t_prev),
                "ts": time.time(),
            },
        )

    return sse_response(gen())

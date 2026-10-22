"""Shared API plumbing: orjson responses, typed errors, request-id middleware."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

import orjson
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from zill.routing.graph import NoRoute, PlaceError
from zill.services import CityNotFound, ShadeUnavailable

log = logging.getLogger("zill.api")

_OPTS = orjson.OPT_SERIALIZE_NUMPY | orjson.OPT_NON_STR_KEYS


class ORJSON(Response):
    """JSON response via orjson (numpy-aware)."""

    media_type = "application/json"

    def render(self, content: Any) -> bytes:
        return orjson.dumps(content, option=_OPTS, default=_default)


def _default(o: Any) -> Any:
    if hasattr(o, "to_dict"):
        return o.to_dict()
    if hasattr(o, "model_dump"):
        return o.model_dump(mode="json")
    raise TypeError(f"not serialisable: {type(o).__name__}")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra


def _err(request: Request, status: int, code: str, message: str, **extra: Any) -> ORJSON:
    rid = getattr(request.state, "request_id", None)
    body = {"error": {"code": code, "message": message, "request_id": rid, **extra}}
    return ORJSON(body, status_code=status, headers={"X-Request-ID": rid or ""})


def install(app: FastAPI) -> None:
    """Install request-id middleware and typed exception handlers (idempotent)."""
    if getattr(app.state, "zill_common_installed", False):
        return
    app.state.zill_common_installed = True

    @app.middleware("http")
    async def request_id_mw(request: Request, call_next):  # type: ignore[no-untyped-def]
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        request.state.request_id = rid
        t0 = time.perf_counter()
        try:
            resp = await call_next(request)
        except Exception:  # last-resort guard; handlers below normally catch first
            log.exception("unhandled error rid=%s %s %s", rid, request.method, request.url.path)
            return _err(request, 500, "internal_error", "Internal server error")
        resp.headers["X-Request-ID"] = rid
        log.info(
            "rid=%s %s %s -> %s %.0fms",
            rid,
            request.method,
            request.url.path,
            resp.status_code,
            (time.perf_counter() - t0) * 1000,
        )
        return resp

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):  # type: ignore[no-untyped-def]
        return _err(request, exc.status, exc.code, exc.message, **exc.extra)

    @app.exception_handler(CityNotFound)
    async def _city_nf(request: Request, exc: CityNotFound):  # type: ignore[no-untyped-def]
        return _err(request, 404, "city_not_found", f"Unknown city {exc.args[0] if exc.args else ''!s}")

    @app.exception_handler(PlaceError)
    async def _place(request: Request, exc: PlaceError):  # type: ignore[no-untyped-def]
        return _err(request, 422, "place_error", str(exc))

    @app.exception_handler(NoRoute)
    async def _noroute(request: Request, exc: NoRoute):  # type: ignore[no-untyped-def]
        return _err(request, 404, "no_route", str(exc) or "No route between these places for this mode")

    @app.exception_handler(ShadeUnavailable)
    async def _shade(request: Request, exc: ShadeUnavailable):  # type: ignore[no-untyped-def]
        return _err(request, 409, "shade_unavailable", str(exc))

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):  # type: ignore[no-untyped-def]
        errs = [{"loc": [str(p) for p in e.get("loc", [])], "msg": e.get("msg", "")} for e in exc.errors()]
        return _err(request, 422, "validation_error", "Invalid request", details=errs)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):  # type: ignore[no-untyped-def]
        return _err(request, exc.status_code, f"http_{exc.status_code}", str(exc.detail))

    @app.exception_handler(Exception)
    async def _any(request: Request, exc: Exception):  # type: ignore[no-untyped-def]
        log.exception("unhandled error: %s", exc)
        return _err(request, 500, "internal_error", "Internal server error")

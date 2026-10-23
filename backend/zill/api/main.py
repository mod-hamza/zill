"""Zill FastAPI app. Other streams add `api/routes_*.py` and register them below."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from zill import config

VERSION = "0.1.0"

app = FastAPI(title="Zill API", version=VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

core = APIRouter(prefix="/api")


@core.get("/health")
def health() -> dict:
    from zill.api.routes_misc import health_payload  # api stream: extended health (city, shade, replay, llm)

    payload = health_payload()
    payload["warm"] = dict(WARM_STATE)
    return payload


@core.get("/config")
def get_config() -> dict:
    return config.public_config()


app.include_router(core)

# Explicit router registration. Streams append their router here, e.g.:
#   from zill.api import routes_cities
#   ROUTERS = [routes_cities.router, ...]
from zill.api import common as _common  # noqa: E402  (api stream: request ids, typed errors)
from zill.api import routes_agent, routes_cities, routes_misc, routes_route  # noqa: E402

_common.install(app)

ROUTERS: list[APIRouter] = [
    routes_cities.router,   # api stream
    routes_route.router,
    routes_misc.router,
    routes_agent.router,    # agent stream
]
for _r in ROUTERS:
    app.include_router(_r)

# --- appended by orchestrator: startup warm-up ---
# The first route on a cold process loads the city, the exposure tables and JIT-compiles numba;
# that can exceed the Next proxy's socket timeout. Warm the exact request path in the background.
WARM_STATE: dict[str, object] = {"done": False, "error": None}


def _warm() -> None:
    import json

    from fastapi.testclient import TestClient

    try:
        hero = json.loads((config.DATA_DIR / "scenarios" / "hero.json").read_text(encoding="utf-8"))
        s = hero["scenarios"][0]
        client = TestClient(app)  # no context manager → no lifespan → no recursion
        client.post(
            "/api/route",
            json={
                "city": config.DEFAULT_CITY,
                "mode": s["mode"],
                "origin": {"lat": s["origin"]["lat"], "lon": s["origin"]["lon"]},
                "dest": {"lat": s["dest"]["lat"], "lon": s["dest"]["lon"]},
                "depart_at": s["depart"],
                "date_key": s["date_id"],
            },
        )
        from zill.agent.backend import ServicesBackend

        ServicesBackend().warm(block=True)
    except Exception as exc:  # warm-up is best effort; never block startup
        WARM_STATE["error"] = repr(exc)
    WARM_STATE["done"] = True


@app.on_event("startup")
def _start_warm() -> None:
    import threading

    threading.Thread(target=_warm, daemon=True, name="zill-startup-warm").start()

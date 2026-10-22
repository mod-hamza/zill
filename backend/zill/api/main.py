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

    return health_payload()


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

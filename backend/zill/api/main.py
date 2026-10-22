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
    return {
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


@core.get("/config")
def get_config() -> dict:
    return config.public_config()


app.include_router(core)

# Explicit router registration. Streams append their router here, e.g.:
#   from zill.api import routes_cities
#   ROUTERS = [routes_cities.router, ...]
ROUTERS: list[APIRouter] = [
    # routes_cities.router,   # api stream
    # routes_route.router,    # api stream
    # routes_agent.router,    # agent stream
]
for _r in ROUTERS:
    app.include_router(_r)

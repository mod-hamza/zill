"""pytest fixtures shared by the routing/API tests (import into test modules)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.synth import FIXTURE_ROOT, build_synth_city


@pytest.fixture(scope="module")
def synth_env():
    import os

    if not (FIXTURE_ROOT / "synth" / "graph.json").exists():
        build_synth_city(FIXTURE_ROOT)
    old = os.environ.get("ZILL_CITIES_DIR")
    os.environ["ZILL_CITIES_DIR"] = str(FIXTURE_ROOT)
    from zill import services

    services.clear_cache()
    yield FIXTURE_ROOT
    if old is None:
        os.environ.pop("ZILL_CITIES_DIR", None)
    else:
        os.environ["ZILL_CITIES_DIR"] = old
    services.clear_cache()


@pytest.fixture(scope="module")
def synth_ctx(synth_env):
    from zill.services import get_city

    return get_city("synth")


@pytest.fixture(scope="module")
def client(synth_env):
    from zill.api.main import app

    return TestClient(app)

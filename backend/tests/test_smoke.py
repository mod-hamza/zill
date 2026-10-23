from fastapi.testclient import TestClient

from zill import brand, config
from zill.api.main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True and j["service"] == "zill"
    assert set(j["llm"]) == {"providers", "model", "key_present"}
    assert isinstance(j["replay"], bool)


def test_config_endpoint_and_no_key():
    r = client.get("/api/config")
    assert r.status_code == 200
    j = r.json()
    assert j["film_duration_s"] == 780
    assert j["lambdas"] == {"fastest": 0, "balanced": 1.0, "coolest": 3.0}
    blob = r.text.lower()
    assert "api_key" not in blob
    if config.LLM_API_KEY:
        assert config.LLM_API_KEY not in r.text
    assert "api_key" not in str(config.public_config()).lower()


def test_brand():
    assert brand.NAME == "Zill & Shams"
    assert brand.SHORT == "Zill"


def test_geo_round_trip():
    import random

    from zill.geo import to_local, to_wgs84

    origin = (config.ORIGIN_LAT, config.ORIGIN_LON)
    rnd = random.Random(1)
    for _ in range(1000):
        x, z = rnd.uniform(-3000, 3000), rnd.uniform(-3000, 3000)
        lat, lon = to_wgs84(x, z, origin)
        x2, z2 = to_local(lat, lon, origin)
        assert abs(x - x2) < 0.01 and abs(z - z2) < 0.01
    assert to_local(config.ORIGIN_LAT + 0.001, config.ORIGIN_LON, origin)[1] < 0

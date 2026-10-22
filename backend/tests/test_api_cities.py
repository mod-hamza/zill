"""Contract tests for the cities / files / shade / sun / build endpoints (synthetic fixture)."""
# ruff: noqa: F811

from __future__ import annotations

from tests.synth_fixtures import client, synth_env  # noqa: F401


def test_cities_list(client):
    r = client.get("/api/cities")
    assert r.status_code == 200
    items = r.json()
    syn = next(c for c in items if c["id"] == "synth")
    assert syn["status"] == "ready" and "summer" in syn["shade_dates"]
    assert set(syn) >= {"id", "name", "origin", "bbox", "counts", "status"}


def test_meta_merges_shade_log(client):
    r = client.get("/api/cities/synth/meta")
    assert r.status_code == 200
    j = r.json()
    steps = [s["step"] for s in j["build_log"]]
    assert steps[:3] == ["geocode", "graph", "ready"] and steps[-1] == "shadow_precompute"
    assert client.get("/api/cities/nope/meta").status_code == 404


def test_files_mime_etag_cache(client):
    r = client.get("/api/cities/synth/files/graph.json")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert "max-age=86400" in r.headers["cache-control"]
    etag = r.headers["etag"]
    r2 = client.get("/api/cities/synth/files/graph.json", headers={"If-None-Match": etag})
    assert r2.status_code == 304
    r3 = client.get("/api/cities/synth/files/exposure_summer.npz")
    assert r3.status_code == 200 and r3.headers["content-type"] == "application/octet-stream"
    assert (
        client.get("/api/cities/synth/files/shade/summer/step_1200.png").headers["content-type"]
        == "image/png"
    )


def test_files_traversal_rejected(client):
    for bad in ("../meta.json", "..%2F..%2Fpyproject.toml", "shade/../../synth/meta.json", "%2e%2e/x"):
        r = client.get(f"/api/cities/synth/files/{bad}")
        assert r.status_code in (400, 404), bad
        assert "error" in r.json() or r.status_code == 404
    assert client.get("/api/cities/synth/files/nope.bin").status_code == 404


def test_shade_png(client):
    r = client.get("/api/shade/synth/summer/1330.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert client.get("/api/shade/synth/summer/0001.png").status_code == 404
    assert client.get("/api/shade/synth/summer/13x0.png").status_code in (400, 404)


def test_sun(client):
    r = client.get("/api/sun", params={"city": "synth", "at": "2026-06-21T12:00:00+04:00"})
    assert r.status_code == 200
    j = r.json()
    assert 80 < j["alt_deg"] <= 90 and len(j["vector"]) == 3 and j["is_night"] is False
    night = client.get("/api/sun", params={"city": "synth", "at": "2026-07-15T02:00:00+04:00"}).json()
    assert night["is_night"] is True
    assert client.get("/api/sun", params={"city": "synth", "at": "garbage"}).status_code == 422


def test_build_replay_sse(client):
    r = client.post("/api/cities/build", params={"city": "synth", "speed": 100})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    body = r.text
    assert "event: build" in body and "event: ready" in body and '"mode":"cached"' in body
    assert client.post("/api/cities/build", params={"city": "atlantis"}).status_code == 404

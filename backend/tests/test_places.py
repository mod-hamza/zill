"""Typed places: folding, index build, ranked search, one-line parsing, online fallback, API, route ids."""

from __future__ import annotations

import json
import shutil
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from tests.synth import FIXTURE_ROOT, build_synth_city
from zill.places import online
from zill.places.build import classify, elements_to_places
from zill.places.fold import fold
from zill.places.index import PlaceIndex
from zill.places.parse import parse_text

NOW = datetime(2026, 10, 23, 10, 0, tzinfo=ZoneInfo("Asia/Dubai"))
ORIGIN = {"lat": 25.1972, "lon": 55.2744}
BBOX = {"s": 25.18, "w": 55.25, "n": 25.21, "e": 55.30}


def _p(pid, name, kind="landmark", alt=(), lat=25.1972, lon=55.2744, **kw):
    return {
        "id": pid, "name": name, "alt_names": list(alt), "kind": kind, "lat": lat, "lon": lon,
        "x": 0.0, "z": 0.0, "node": 0, "snap_m": 1.0, **kw,
    }  # fmt: skip


@pytest.fixture(scope="module")
def index():
    places = [
        _p("burj", "Burj Khalifa", "landmark", ["برج خليفة"]),
        _p("burj_lake", "Burj Khalifa Lake", "park", lon=55.2760),
        _p("dmall", "The Dubai Mall", "mall", ["دبي مول"], lon=55.2790),
        _p("opera", "Dubai Opera", "landmark", lon=55.2700),
        _p("metro", "Burj Khalifa/Dubai Mall Metro Station", "station", lon=55.2800),
        _p("st", "Sheikh Mohammed bin Rashid Boulevard", "street", lon=55.2720),
        _p("oslo_s", "Oslo S", "station", ["Oslo Sentralstasjon", "Oslo Central Station"]),
        _p("aker", "Aker Brygge", "square", lon=55.2600),
        _p("ostre", "Østre Aker kirke", "landmark", ["Oestre Aker Church"], lon=55.2650),
        _p("cafe1", "Café Åsgård", "food", lon=55.2610),
        _p("sb1", "Starbucks", "food", lon=55.2610),
        _p("sb2", "Starbucks", "food", lon=55.2900),
    ]
    return PlaceIndex("t", places)


# -- folding ---------------------------------------------------------------------------------
def test_fold_accents_case_and_nordic_letters():
    assert fold("Østre Åker Ærø") == "ostre aker aero"
    assert fold("CAFÉ  Åsgård!") == "cafe asgard"
    assert fold("Straße") == "strasse"


def test_fold_arabic_variants_and_digits():
    assert fold("أبو ظبي") == fold("ابو ظبي")
    assert fold("مَدينة") == fold("مدينة")  # diacritics stripped
    assert fold("ة") == fold("ه") and fold("ى") == fold("ي")
    assert fold("شارع ١٢") == "شارع 12"


# -- classification and build ---------------------------------------------------------------
def test_classify_kinds():
    assert classify({"railway": "station", "name": "x"}, "node") == "station"
    assert classify({"tourism": "hotel"}, "way") == "hotel"
    assert classify({"shop": "mall"}, "way") == "mall"
    assert classify({"highway": "residential"}, "way") == "street"
    assert classify({"highway": "bus_stop"}, "node") == "stop"
    assert classify({"amenity": "cafe"}, "node") == "food"
    assert classify({"boundary": "administrative", "admin_level": "8"}, "relation") is None
    assert classify({"barrier": "fence"}, "way") is None


def test_elements_to_places_merges_streets_dedupes_and_ids():
    els = [
        {"type": "node", "id": 1, "lat": 25.1972, "lon": 55.2744,
         "tags": {"name": "Zed Tower", "name:ar": "برج زد", "tourism": "attraction"}},
        {"type": "way", "id": 2, "center": {"lat": 25.1972, "lon": 55.2744},
         "tags": {"name": "Zed Tower", "building": "yes"}},  # same name and place: dropped
        {"type": "way", "id": 3, "center": {"lat": 25.1980, "lon": 55.2750},
         "tags": {"name": "Long Street", "highway": "residential"}},
        {"type": "way", "id": 4, "center": {"lat": 25.1990, "lon": 55.2760},
         "tags": {"name": "Long Street", "highway": "residential"}},
        {"type": "node", "id": 5, "lat": 25.1975, "lon": 55.2745,
         "tags": {"name": "Pole", "barrier": "gate"}},
        {"type": "node", "id": 6, "lat": 26.0, "lon": 55.2745, "tags": {"name": "Far", "shop": "kiosk"}},
        {"type": "node", "id": 7, "lat": 25.1976, "lon": 55.2745, "tags": {"name": "L", "amenity": "bench"}},
    ]
    out = elements_to_places(els, ORIGIN, BBOX)
    names = sorted(p["name"] for p in out)
    assert names == ["Long Street", "Zed Tower"]
    tower = next(p for p in out if p["name"] == "Zed Tower")
    assert tower["kind"] == "landmark" and "برج زد" in tower["alt_names"]
    assert isinstance(tower["x"], float) and len({p["id"] for p in out}) == 2


# -- search ---------------------------------------------------------------------------------
def top(index, q, n=1):
    return [r["id"] for r in index.search(q, limit=n)]


def test_search_exact_prefix_case_and_accent_insensitive(index):
    assert top(index, "burj khalifa") == ["burj"]
    assert top(index, "BURJ KH") == ["burj"]
    assert top(index, "cafe asgard") == ["cafe1"]
    assert top(index, "Café Åsgård") == ["cafe1"]


def test_search_nordic_and_arabic_folding(index):
    assert top(index, "ostre aker") == ["ostre"]
    assert top(index, "Østre Aker kirke") == ["ostre"]
    assert top(index, "oestre aker church") == ["ostre"]
    assert top(index, "oslo sentralstasjon") == ["oslo_s"]
    assert top(index, "برج خليفة") == ["burj"]
    assert top(index, "برج خَليفه") == ["burj"]  # diacritics + taa marbuta/haa folded


def test_search_article_token_and_fuzzy(index):
    assert top(index, "dubai mall") == ["dmall"]  # leading "The" optional
    assert top(index, "mohammed rashid boulevard")[0] == "st"  # tokens in any order/gaps
    assert top(index, "dubay opra")[0] == "opera"  # typos
    assert top(index, "oslo")[0] == "oslo_s"


def test_search_kind_weight_prefers_landmarks_over_street_like_names(index):
    ids = top(index, "burj", n=3)
    assert ids[0] == "burj"


def test_search_returns_matched_alias_and_filters(index):
    r = index.search("oslo central", limit=1)[0]
    assert r["id"] == "oslo_s" and r["matched"] == "Oslo Central Station"
    assert [x["id"] for x in index.search("burj", kinds={"park"})] == ["burj_lake"]
    assert index.search("zzzzqqq") == []
    assert index.search("") == []


def test_search_is_fast_on_a_realistic_index():
    names = [f"Place {i} {w}" for i, w in enumerate(["Tower", "Cafe", "Street", "Mall", "Park"] * 300)]
    big = PlaceIndex("big", [_p(f"p{i}", n, lon=55.27 + i * 1e-6) for i, n in enumerate(names)])
    big.search("tower")  # warm
    t0 = time.perf_counter()
    for q in ("place 77 tow", "mall 4", "cafee", "park"):
        big.search(q, limit=8)
    assert (time.perf_counter() - t0) / 4 < 0.020  # <= 20 ms per query on 1,500 places (Dubai has ~1,070)


# -- parse ----------------------------------------------------------------------------------
def parse(index, text, **kw):
    def searcher(_city, q, limit):
        return index.search(q, limit=limit)

    return parse_text("t", text, now=NOW, searcher=searcher, **kw)


@pytest.mark.parametrize(
    "text",
    [
        "from Burj Khalifa to Dubai Opera",
        "Burj Khalifa to Dubai Opera",
        "burj khalifa → dubai opera",
        "Burj Khalifa -> Dubai Opera",
        "Burj Khalifa - Dubai Opera",
        "من برج خليفة إلى Dubai Opera",
    ],
)
def test_parse_separators(index, text):
    r = parse(index, text)
    assert r["origin"]["id"] == "burj" and r["dest"]["id"] == "opera", text
    assert r["confidence"] > 0.8


def test_parse_time_mode_preference(index):
    r = parse(index, "from Dubai Mall to Dubai Opera at 15:30 by bike sunny")
    assert (r["origin"]["id"], r["dest"]["id"]) == ("dmall", "opera")
    assert r["depart_at"] == "2026-10-23T15:30:00+04:00" and r["depart_time"] == "15:30"
    assert r["mode"] == "cycle" and r["preference"] == "sun"


def test_parse_tomorrow_ampm_and_leading_words(index):
    r = parse(index, "shady walk from Burj Khalifa to Dubai Mall tomorrow 9am")
    assert r["depart_at"] == "2026-10-24T09:00:00+04:00"
    assert r["mode"] == "walk" and r["preference"] == "shade"
    assert r["dest"]["id"] == "dmall"
    r2 = parse(index, "Burj Khalifa to Dubai Opera, 5pm, scooter")
    assert r2["depart_time"] == "17:00" and r2["mode"] == "scooter"
    r3 = parse(index, "Burj Khalifa to Dubai Opera tomorrow")
    assert r3["depart_date"] == "2026-10-24" and "depart_at" not in r3


def test_parse_no_options_and_single_place(index):
    r = parse(index, "Burj Khalifa to Dubai Opera")
    assert not {"depart_at", "mode", "preference"} & set(r)
    one = parse(index, "Dubai Opera")
    assert one["origin"] is None and one["dest"]["id"] == "opera" and one["confidence"] == 0.0


def test_parse_ambiguity_gives_candidates(index):
    r = parse(index, "Starbucks to Dubai Opera")
    assert r["ambiguous"]["origin"] is True  # two far-apart branches with the same name
    assert len(r["origin_candidates"]) >= 2 and r["confidence"] < 0.9
    r2 = parse(index, "Burj Khalifa to Dubai Opera")
    assert r2["ambiguous"] == {"origin": False, "dest": False}


def test_parse_unknown_text_has_low_confidence(index):
    r = parse(index, "qqqq to zzzz")
    assert r["origin"] is None and r["dest"] is None and r["confidence"] == 0.0


# -- online fallback (never touches the network) -----------------------------------------------
@pytest.fixture
def fake_online(monkeypatch):
    online.clear()
    monkeypatch.setenv("ZILL_ONLINE_GEOCODE", "1")
    calls: list[dict] = []

    def fake(url, params):
        calls.append(params)
        return [{"lat": "25.1975", "lon": "55.2750", "name": "Fake Kiosk", "osm_type": "node",
                 "osm_id": 42, "display_name": "Fake Kiosk, Dubai"},
                {"lat": "30.0", "lon": "50.0", "name": "Outside", "osm_type": "node", "osm_id": 43,
                 "display_name": "x"}]  # fmt: skip

    monkeypatch.setattr(online, "transport", fake)
    monkeypatch.setattr(online, "MIN_INTERVAL_S", 0.0)
    yield calls
    online.clear()


def test_online_search_bounded_labelled_cached(fake_online):
    r = online.search("t", BBOX, "fake kiosk")
    assert [p["name"] for p in r] == ["Fake Kiosk"]  # out-of-bbox row dropped
    assert r[0]["source"] == "online" and r[0]["id"] == "online_n42"
    p = fake_online[0]
    assert p["bounded"] == 1 and p["viewbox"] == f"{BBOX['w']},{BBOX['n']},{BBOX['e']},{BBOX['s']}"
    online.search("t", BBOX, "Fake  Kiosk")  # same folded query -> cache
    assert len(fake_online) == 1


def test_online_disabled_and_short_and_failures(fake_online, monkeypatch):
    monkeypatch.setenv("ZILL_ONLINE_GEOCODE", "0")
    assert online.search("t", BBOX, "fake kiosk") == [] and fake_online == []
    monkeypatch.setenv("ZILL_ONLINE_GEOCODE", "1")
    assert online.search("t", BBOX, "ab") == []

    def boom(url, params):
        raise TimeoutError

    monkeypatch.setattr(online, "transport", boom)
    assert online.search("t", BBOX, "something else") == []


def test_online_rate_limit_skips_when_budget_exhausted(fake_online, monkeypatch):
    monkeypatch.setattr(online, "MIN_INTERVAL_S", 100.0)
    monkeypatch.setattr(online, "MAX_WAIT_S", 0.1)
    assert online.search("t", BBOX, "first query") != []  # the first call takes the slot
    n = len(fake_online)
    assert online.search("t", BBOX, "second query") == []  # next slot is 100 s away: no request
    assert len(fake_online) == n


def test_user_agent_has_no_email():
    assert online.USER_AGENT == "Zill-hackathon-prototype/0.1" and "@" not in online.USER_AGENT


# -- API + /api/route integration ---------------------------------------------------------------
@pytest.fixture(scope="module")
def api(tmp_path_factory):
    import os

    if not (FIXTURE_ROOT / "synth" / "graph.json").exists():
        build_synth_city(FIXTURE_ROOT)
    root = tmp_path_factory.mktemp("cities")
    shutil.copytree(FIXTURE_ROOT / "synth", root / "synth")
    pois = json.loads((root / "synth" / "pois.json").read_text(encoding="utf-8"))["pois"]
    by = {p["id"]: p for p in pois}

    def mk(pid, name, kind, src, alt=()):
        s = by[src]
        return {"id": pid, "name": name, "alt_names": list(alt), "kind": kind, "lat": s["lat"],
                "lon": s["lon"], "x": s["x"], "z": s["z"], "node": s["node"], "snap_m": 0.0,
                "osm": f"node/{abs(hash(pid)) % 10**6}"}  # fmt: skip

    places = [
        mk("zz_tower", "Zuhr Tower", "landmark", "nw_corner", ["برج الظهر"]),
        mk("zz_cafe", "Café Øst", "food", "ne_corner", ["Oest Cafe"]),
    ]
    (root / "synth" / "places.json").write_text(json.dumps({"places": places}), encoding="utf-8")
    old = os.environ.get("ZILL_CITIES_DIR")
    os.environ["ZILL_CITIES_DIR"] = str(root)
    os.environ["ZILL_ONLINE_GEOCODE"] = "0"
    os.environ["ZILL_WEATHER_LIVE"] = "0"
    from zill import services
    from zill.api.main import app
    from zill.places.index import clear_cache

    services.clear_cache()
    clear_cache()
    yield TestClient(app)
    for k, v in (("ZILL_CITIES_DIR", old), ("ZILL_ONLINE_GEOCODE", None), ("ZILL_WEATHER_LIVE", None)):
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    services.clear_cache()
    clear_cache()


def test_api_search(api):
    r = api.get("/api/places/search", params={"city": "synth", "q": "zuhr", "limit": 5})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["results"][0]["id"] == "zz_tower" and j["results"][0]["node"] == 0
    assert j["timing_ms"] < 200 and {"lat", "lon", "kind", "score", "source"} <= set(j["results"][0])
    r2 = api.get("/api/places/search", params={"city": "synth", "q": "oest cafe"})
    assert r2.json()["results"][0]["id"] == "zz_cafe"
    assert api.get("/api/places/search", params={"city": "synth", "q": "north west"}).json()["results"][0][
        "id"
    ] == "nw_corner"  # curated POIs are searchable too


def test_api_search_validation(api):
    assert api.get("/api/places/search", params={"city": "nope", "q": "x"}).status_code == 404
    assert api.get("/api/places/search", params={"city": "synth", "q": "x" * 201}).status_code == 422
    assert api.get("/api/places/search", params={"city": "synth", "q": ""}).status_code == 422
    assert api.get("/api/places/search", params={"city": "synth", "q": "a", "limit": 99}).status_code == 422


def test_api_parse(api):
    r = api.post(
        "/api/places/parse",
        json={"city": "synth", "text": "from North West Plaza to Zuhr Tower at 14:30 by bike, sunny"},
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["origin"]["id"] == "nw_corner" and j["dest"]["id"] == "zz_tower"
    assert j["mode"] == "cycle" and j["preference"] == "sun" and j["depart_time"] == "14:30"
    assert j["depart_at"].endswith("+04:00")
    assert api.post("/api/places/parse", json={"city": "synth", "text": ""}).status_code == 422
    assert api.post("/api/places/parse", json={"city": "synth", "text": "x" * 301}).status_code == 422


def test_route_accepts_index_place_ids(api):
    body = {
        "city": "synth", "mode": "walk", "origin": "zz_tower", "dest": "zz_cafe",
        "depart_at": "2026-07-15T14:30:00+04:00",
    }  # fmt: skip
    r = api.post("/api/route", json=body)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["origin"]["node"] == 0 and j["dest"]["node"] == 5 and j["origin"]["name"] == "Zuhr Tower"
    body["origin"] = {"poi": "zz_tower"}
    assert api.post("/api/route", json=body).status_code == 200
    body["origin"] = "no_such_place"
    assert api.post("/api/route", json=body).status_code in (404, 422)


def test_route_accepts_online_place_ids(api, monkeypatch):
    online.clear()
    monkeypatch.setenv("ZILL_ONLINE_GEOCODE", "1")
    pois = api.get("/api/cities/synth/files/pois.json").json()["pois"]
    s = pois[2]
    monkeypatch.setattr(online, "MIN_INTERVAL_S", 0.0)
    monkeypatch.setattr(
        online,
        "transport",
        lambda url, params: [{"lat": str(s["lat"]), "lon": str(s["lon"]), "name": "Pop Up Stall",
                              "osm_type": "node", "osm_id": 777, "display_name": "Pop Up Stall"}],
    )  # fmt: skip
    r = api.get("/api/places/search", params={"city": "synth", "q": "pop up stall"})
    hit = r.json()["results"][0]
    assert hit["source"] == "online" and hit["id"] == "online_n777"
    body = {"city": "synth", "mode": "walk", "origin": hit["id"], "dest": "zz_cafe",
            "depart_at": "2026-07-15T14:30:00+04:00"}  # fmt: skip
    assert api.post("/api/route", json=body).status_code == 200
    online.clear()

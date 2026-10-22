"""City-agnostic bake on a tiny synthetic bbox, network disabled (PRD 6.9, 18.1)."""

import json
from pathlib import Path

import pytest

from zill.data import bake as bake_mod
from zill.data import cities, overpass

FIX = Path(__file__).parent / "fixtures"


def _fixture_transport(url: str, query: str) -> dict:
    if 'nwr["name"]' in query:
        name = "pois"
    elif "natural" in query:
        name = "trees"
    elif "building" in query:
        name = "buildings"
    else:
        name = "roads"
    return json.loads((FIX / f"overpass_{name}.json").read_text())


@pytest.fixture(scope="module")
def baked(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("bake")
    mp = pytest.MonkeyPatch()
    reg = tmp / "cities.json"
    reg.write_text(
        json.dumps(
            [
                {
                    "city_id": "synthetic",
                    "name": "Synthetic Test City",
                    "bbox": {"s": 9.998, "w": 19.998, "n": 10.002, "e": 20.002},
                    "origin": {"lat": 10.0, "lon": 20.0},
                    "timezone": "UTC",
                }
            ]
        )
    )
    cur = tmp / "curated" / "synthetic"
    cur.mkdir(parents=True)
    (cur / "gazetteer.json").write_text(
        json.dumps(
            [
                {
                    "id": "tower",
                    "name": "Test Tower",
                    "kind": "landmark",
                    "hint": {"lat": 9.9999, "lon": 20.0001},
                    "match": ["test tower"],
                },
                {
                    "id": "ghost",
                    "name": "Ghost Place",
                    "kind": "park",
                    "hint": {"lat": 10.001, "lon": 20.001},
                },
            ]
        )
    )

    def no_network(url, query):
        raise AssertionError("network disabled in tests")

    mp.setattr(cities, "REGISTRY", reg)
    mp.setattr(bake_mod, "CURATED_DIR", tmp / "curated")
    mp.setattr(overpass, "RAW_DIR", tmp / "raw")
    mp.setattr(overpass, "transport", _fixture_transport)
    meta = bake_mod.bake("synthetic", out_root=tmp / "cities", run_hooks=False)
    # second bake must hit the cache only
    mp.setattr(overpass, "transport", no_network)
    meta2 = bake_mod.bake("synthetic", out_root=tmp / "cities", run_hooks=False)
    mp.undo()
    out = tmp / "cities" / "synthetic"
    return meta, meta2, out


def _load(out, name):
    return json.loads((out / name).read_text(encoding="utf-8"))


def test_outputs_exist(baked):
    _, _, out = baked
    for f in [
        "meta.json",
        "buildings.json",
        "buildings.glb",
        "trees.json",
        "graph.json",
        "links.geojson",
        "pois.json",
        "glb_report.json",
    ]:
        assert (out / f).exists(), f


def test_cache_rerun(baked):
    meta, meta2, _ = baked
    assert meta2["diagnostics"]["overpass_requests"] == 0
    assert meta2["counts"] == meta["counts"]


def test_height_rules(baked):
    _, _, out = baked
    b = {x["osm"]: x for x in _load(out, "buildings.json")["buildings"]}
    assert "way/1" not in b, "shell with parts must be dropped"
    assert b["way/2"]["height"] == pytest.approx(120.0) and b["way/2"]["source"] == "part"
    assert b["way/3"]["height"] == pytest.approx(34.0)
    assert b["way/2"]["name"] == "Test Tower"  # tallest part inherits shell name
    assert b["way/4"]["height"] == pytest.approx(5 * 3.4 + 3.0) and b["way/4"]["source"] == "levels"
    assert b["way/5"]["height"] == pytest.approx(45.0) and b["way/5"]["source"] == "fallback"
    assert b["way/6"]["height"] == pytest.approx(30.48) and b["way/6"]["source"] == "tag"
    assert b["relation/7"]["height"] == pytest.approx(22.0) and len(b["relation/7"]["holes"]) == 1
    assert "way/9" not in b, "slivers < 4 m2 dropped"
    # parts covering < 50% of a shell: shell kept minus the part footprint
    assert b["way/10"]["height"] == pytest.approx(20.0) and b["way/11"]["height"] == pytest.approx(12.0)
    assert b["way/10"]["source"] == "tag"
    fp = b["way/5"]["footprint"]
    assert fp[0] != fp[-1] and len(fp) == 4


def test_meta_contract(baked):
    meta, _, out = baked
    m = _load(out, "meta.json")
    for k in [
        "city_id",
        "origin",
        "bbox_core",
        "bbox_caster",
        "bbox_scene",
        "core_grid",
        "caster_grid",
        "counts",
        "height_sources",
        "dropped_components",
        "max_building_height_m",
        "source",
        "attribution",
        "dates",
        "build_log",
    ]:
        assert k in m
    assert m["core_grid"]["x0"] % 2 == 0 and m["core_grid"]["res_m"] == 2.0
    assert m["caster_grid"]["cols"] > m["core_grid"]["cols"]
    assert m["height_sources"] == {"tag": 2, "levels": 1, "fallback": 2, "landmark": 0, "part": 3}
    steps = [s["step"] for s in m["build_log"]]
    assert steps == [
        "geocode",
        "fetch_buildings",
        "fetch_roads",
        "fetch_trees",
        "heights",
        "graph",
        "covered_links",
        "write",
    ]
    assert m["max_building_height_m"] == pytest.approx(120.0)


def test_graph(baked):
    _, _, out = baked
    g = _load(out, "graph.json")
    E, N = g["edges"], g["nodes"]
    n = len(E["u"])
    assert all(len(E[k]) == n for k in E)
    by = {}
    for i in range(n):
        by.setdefault(E["osm"][i], []).append(i)
    # residential split at shared nodes 102, 103 -> 3 edges
    assert len(by["way/201"]) == 3
    # steps: walk only
    i = by["way/203"][0]
    assert E["stairs"][i] and E["walk"][i] and not E["cycle"][i] and not E["scooter"][i]
    # primary foot=no: cycle only
    i = by["way/205"][0]
    assert E["cycle"][i] and not E["walk"][i]
    # covered + indoor (entrance-tagged transition)
    assert E["cls"][by["way/204"][0]] == "covered"
    assert E["cls"][by["way/206"][0]] == "indoor"
    # private service and the disconnected footway are gone; indoor edge with no entrance is cut off
    assert "way/207" not in by and "way/208" not in by and "way/209" not in by
    assert sum(N["crossing"]) == 1 and sum(N["entrance"]) >= 1
    assert all(len(geom) >= 4 for geom in E["geom"])


def test_trees_pois_links(baked):
    meta, _, out = baked
    trees = _load(out, "trees.json")["trees"]
    assert len(trees) == 1 + 6
    assert {t["src"] for t in trees} == {"node", "row"}
    pois = {p["id"]: p for p in _load(out, "pois.json")["pois"]}
    assert pois["tower"]["source"] == "osm" and pois["ghost"]["source"] == "curated"
    assert "test_hotel" in pois
    assert all(isinstance(p["node"], int) for p in pois.values())
    links = _load(out, "links.geojson")
    assert {f["properties"]["cls"] for f in links["features"]} == {"covered", "indoor"}
    assert meta["counts"]["covered_edges"] == 1


def test_glb_loads(baked):
    import trimesh

    _, _, out = baked
    sc = trimesh.load(str(out / "buildings.glb"), force="scene")
    assert len(sc.geometry) >= 1
    assert sc.bounds[1][1] == pytest.approx(120.0, abs=0.01)
    import numpy as np

    for g in sc.geometry.values():
        tri = g.vertices[g.faces]
        fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        vn = g.vertex_normals[g.faces].mean(axis=1)
        assert (np.einsum("ij,ij->i", fn, vn) > 0).all(), "winding must agree with normals (CCW front faces)"
    # custom attributes present in the glTF JSON
    import struct

    raw = (out / "buildings.glb").read_bytes()
    jlen = struct.unpack("<I", raw[12:16])[0]
    gl = json.loads(raw[20 : 20 + jlen])
    attrs = gl["meshes"][0]["primitives"][0]["attributes"]
    assert {"POSITION", "NORMAL", "_BUILDING_ID", "_HEIGHT"} <= set(attrs)
    assert all(n["name"].startswith("tile_") for n in gl["nodes"])
    rep = _load(out, "glb_report.json")
    assert rep["verify"]["loaded"] and rep["triangles"] > 0

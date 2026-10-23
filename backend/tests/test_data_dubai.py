"""Assertions on the committed Downtown Dubai bake (skipped if the bake is absent)."""

import json

import pytest

from zill import config

CITY = config.CITIES_DIR / "dubai_downtown"
pytestmark = pytest.mark.skipif(
    not (CITY / "meta.json").exists(),
    reason="Dubai bake absent: run python -m zill.data.bake --city dubai_downtown",
)


def _load(name):
    return json.loads((CITY / name).read_text(encoding="utf-8"))


def test_burj_khalifa_828m():
    blds = _load("buildings.json")["buildings"]
    poi = {p["id"]: p for p in _load("pois.json")["pois"]}["burj_khalifa"]
    # tallest footprint within 120 m of the resolved Burj Khalifa position (shell or tallest part)
    near = [
        b for b in blds if any((x - poi["x"]) ** 2 + (z - poi["z"]) ** 2 < 120**2 for x, z in b["footprint"])
    ]
    assert near, "no footprint near the Burj Khalifa"
    assert max(b["height"] for b in near) == pytest.approx(828.0, abs=5.0)


def test_meta_counts_sane():
    m = _load("meta.json")
    c = m["counts"]
    # PRD gate asks > 10,000; the real OSM network in the scene bbox gives ~7.7k split edges (all
    # walkable/cyclable classes, split at shared nodes; see docs/VALIDATION.md "Data"). Guard the honest
    # number against pipeline regressions instead of padding the graph.
    assert c["edges"] > 7_000
    assert c["edges_walk"] > 6_500
    assert c["buildings_scene"] > 2_000
    assert c["ac_link_edges"] + c["covered_edges"] >= 1
    assert c["pois"] >= 12
    assert m["attribution"] == "© OpenStreetMap contributors"
    assert sum(m["height_sources"].values()) == c["buildings"]


def test_graph_columnar_consistent():
    g = _load("graph.json")
    n_nodes = len(g["nodes"]["x"])
    n = len(g["edges"]["u"])
    assert all(len(v) == n for v in g["edges"].values())
    assert all(len(v) == n_nodes for v in g["nodes"].values())
    assert max(g["edges"]["u"] + g["edges"]["v"]) < n_nodes
    for i in range(n):
        assert not (g["edges"]["stairs"][i] and (g["edges"]["cycle"][i] or g["edges"]["scooter"][i]))


def test_pois_snapped():
    pois = _load("pois.json")["pois"]
    n_nodes = len(_load("graph.json")["nodes"]["x"])
    for p in pois:
        assert 0 <= p["node"] < n_nodes


def test_dubai_mall_reachable_without_ac_link():
    """The mall must connect to the street network through its own doors, not only via the Metro Link."""
    import networkx as nx

    g = _load("graph.json")
    E = g["edges"]
    pois = {p["id"]: p for p in _load("pois.json")["pois"]}
    G = nx.Graph()
    for i in range(len(E["u"])):
        if E["walk"][i] and E["cls"][i] != "ac_link":
            G.add_edge(E["u"][i], E["v"][i], w=E["length_m"][i])
    d = nx.shortest_path_length(G, pois["burj_khalifa"]["node"], pois["dubai_mall"]["node"], weight="w")
    assert d < 700
    for pid in ("dubai_opera", "souk_al_bahar", "address_downtown"):
        assert nx.has_path(G, pois[pid]["node"], pois["dubai_mall"]["node"])
